#include "inference_acl.h"

#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fstream>
#include <functional>
#include <future>
#include <iomanip>
#include <iostream>
#include <memory>
#include <queue>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

using json = nlohmann::json;

namespace {

// Tracks RunGraphAsync callbacks still in flight. On timeout the caller waits for
// pending callbacks before destroying inputs/session; if they never finish, the
// process exits without unwinding to avoid use-after-free.
struct RunLifetime {
  std::atomic<int> pending{0};
  std::atomic<bool> timed_out{false};
  std::mutex mu;
  std::condition_variable cv;

  void Add() { pending.fetch_add(1); }

  void Done() {
    if (pending.fetch_sub(1) == 1) cv.notify_all();
  }

  bool WaitZero(int seconds) {
    std::unique_lock<std::mutex> lock(mu);
    return cv.wait_for(lock, std::chrono::seconds(seconds),
                       [this] { return pending.load() == 0; });
  }
};

int TimeoutFromEnv(const char *key, int def) {
  int64_t value = def;
  if (!ParseEnvInt(key, def, value) || value <= 0) return def;
  return static_cast<int>(value);
}

int WarmupTimeoutSec() { return TimeoutFromEnv("WARMUP_TIMEOUT_SEC", 1200); }
int RunTimeoutSec() { return TimeoutFromEnv("RUN_TIMEOUT_SEC", 300); }
int TimeoutGraceSec() { return TimeoutFromEnv("TIMEOUT_GRACE_SEC", 30); }

std::string NowString() {
  std::time_t t = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
  char buf[64];
  struct tm tmv;
  std::strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", localtime_r(&t, &tmv));
  return std::string(buf);
}

[[noreturn]] void HardExitTimeout(uint32_t index, const std::string &stage,
                                  const std::string &detail) {
  std::ostringstream oss;
  oss << TPrefix(index) << "[ERROR] stage=" << stage << " result=timeout " << detail;
  const std::string line = oss.str();
  std::cerr << line << std::endl;
  std::cerr.flush();
  std::_Exit(1);
}

}  // namespace

InferenceAcl::InferenceAcl(const IoConfig &io, ge::GeSession *sess, uint32_t graph_id,
                           uint32_t index, uint32_t device_id, RunStats *stats,
                           std::atomic<bool> *stop)
    : io_(io),
      sess_(sess),
      graph_id_(graph_id),
      index_(index),
      device_id_(device_id),
      stats_(stats),
      stop_(stop),
      batch_list_path_(io.batch_list),
      output_dir_(io.output_dir) {}

InferenceAcl::~InferenceAcl() {
  DestroyInput();
  if (device_set_) {
    aclrtResetDevice(device_id_);
    device_set_ = false;
  }
}

void InferenceAcl::LogError(const std::string &stage, const std::string &obj, long ret,
                            const std::string &reason) {
  std::ostringstream oss;
  oss << "[ERROR] stage=" << stage << " obj=" << obj << " ret=" << ret;
  if (!reason.empty()) oss << " reason=" << reason;
  std::string line = oss.str();
  std::cout << line << std::endl;
  std::string path = GetEnv("GE_ERROR_LOG", "");
  if (path.empty()) return;
  std::ofstream of(path, std::ios::app);
  if (!of.is_open()) return;
  std::time_t t = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
  char buf[64];
  struct tm tmv;
  std::strftime(buf, sizeof(buf), "%Y-%m-%d %H:%M:%S", localtime_r(&t, &tmv));
  of << buf << " " << line;
  if (GetEnv("ERROR_LOG_LEVEL", "brief") == "full") {
    of << " | thread_index=" << index_ << " model=" << io_.model_file;
  }
  of << std::endl;
}

Result InferenceAcl::ParseInputJson() {
  std::cout << TPrefix(index_) << "[GE INPUT] batch_list=" << batch_list_path_ << std::endl;
  std::ifstream f(batch_list_path_);
  if (!f.is_open()) {
    LogError("ParseInputJson", batch_list_path_, 0, "open json failed");
    return FAILED;
  }
  try {
    f >> j_;
  } catch (const std::exception &e) {
    LogError("ParseInputJson", batch_list_path_, 0, std::string("parse failed: ") + e.what());
    return FAILED;
  }
  if (!j_.is_array()) {
    LogError("ParseInputJson", batch_list_path_, 0, "expect array");
    return FAILED;
  }
  return SUCCESS;
}

Result InferenceAcl::ParseInput() {
  if (ParseInputJson() != SUCCESS) return FAILED;
  inputs_.clear();
  input_host_data_.clear();
  total_size_ = 0;
  std::string tp = TPrefix(index_);
  try {
    for (size_t i = 0; i < j_.size(); i++) {
      if (ParseSingleInput(j_[i], static_cast<uint32_t>(i)) != SUCCESS) return FAILED;
    }
  } catch (const std::exception &e) {
    LogError("ParseInput", "batch_list", 0, std::string("parse failed: ") + e.what());
    return FAILED;
  }
  std::cout << tp << "[GE INPUT] total: items=" << j_.size() << " | bytes=" << total_size_
            << " | placement=host" << std::endl;
  return SUCCESS;
}

Result InferenceAcl::ParseSingleInput(const json &json_obj, uint32_t index) {
  if (!json_obj.is_object() ||
      !JsonHas(json_obj, {"size", "item_feature", "dim", "ori_batch", "ori_name"})) {
    LogError("ParseSingleInput", "batch_list item", index, "missing required field");
    return FAILED;
  }
  size_t data_size = json_obj["size"];
  size_t item_feature = json_obj["item_feature"];
  std::vector<int64_t> shape = json_obj["dim"];
  size_t dim0 = shape.empty() ? 1 : shape[0];
  size_t target_dim = dim0;
  size_t ori_batch = json_obj["ori_batch"];
  const bool keep_dims = GetEnvBool("KeepDims", false);
  if (item_feature == 1 && !keep_dims) {
    if (dim0 == ori_batch) {
      data_size *= io_.batch_size;
    } else {
      data_size *= dim0;
    }
  }
  if (target_dim != 1 && ori_batch == dim0 && !keep_dims) {
    target_dim = io_.batch_size;
    shape[0] = io_.batch_size;
  }

  std::string ori_name = json_obj["ori_name"];
  ge::DataType input_dtype = ge::DT_FLOAT;
  std::shared_ptr<InputDataBase> data;
  json val_j;
  if (json_obj.contains("int64_val")) {
    input_dtype = ge::DT_INT64;
    val_j = json_obj["int64_val"];
    data = (item_feature == 0) ? std::shared_ptr<InputDataBase>(new InputData<int64_t>(val_j))
                               : std::shared_ptr<InputDataBase>(new InputData<int64_t>(val_j, target_dim, dim0));
  } else if (json_obj.contains("float_val")) {
    input_dtype = ge::DT_FLOAT;
    val_j = json_obj["float_val"];
    data = (item_feature == 0) ? std::shared_ptr<InputDataBase>(new InputData<float>(val_j))
                               : std::shared_ptr<InputDataBase>(new InputData<float>(val_j, target_dim, dim0));
  } else if (json_obj.contains("float16_bits")) {
    input_dtype = ge::DT_FLOAT16;
    val_j = json_obj["float16_bits"];
    data = (item_feature == 0) ? std::shared_ptr<InputDataBase>(new InputData<uint16_t>(val_j))
                               : std::shared_ptr<InputDataBase>(new InputData<uint16_t>(val_j, target_dim, dim0));
  } else if (json_obj.contains("bfloat16_bits")) {
    input_dtype = ge::DT_BF16;
    val_j = json_obj["bfloat16_bits"];
    data = (item_feature == 0) ? std::shared_ptr<InputDataBase>(new InputData<uint16_t>(val_j))
                               : std::shared_ptr<InputDataBase>(new InputData<uint16_t>(val_j, target_dim, dim0));
  } else if (json_obj.contains("int32_val")) {
    input_dtype = ge::DT_INT32;
    val_j = json_obj["int32_val"];
    data = (item_feature == 0) ? std::shared_ptr<InputDataBase>(new InputData<int32_t>(val_j))
                               : std::shared_ptr<InputDataBase>(new InputData<int32_t>(val_j, target_dim, dim0));
  } else if (json_obj.contains("bool_val")) {
    input_dtype = ge::DT_BOOL;
    val_j = json_obj["bool_val"];
    data = (item_feature == 0) ? std::shared_ptr<InputDataBase>(new InputData<uint8_t>(val_j))
                               : std::shared_ptr<InputDataBase>(new InputData<uint8_t>(val_j, target_dim, dim0));
  } else {
    LogError("ParseSingleInput", ori_name, 0, "unsupported value key");
    return FAILED;
  }
  if (data_size != data->GetSize()) {
    LogError("ParseSingleInput", ori_name, static_cast<long>(data->GetSize()),
             "size mismatch");
    return FAILED;
  }
  input_host_data_.emplace_back(data);
  total_size_ += data->GetSize();

  std::initializer_list<int64_t> empty;
  gert::StorageShape storage(empty, empty);
  for (auto d : shape) {
    storage.MutableOriginShape().AppendDim(d);
    storage.MutableStorageShape().AppendDim(d);
  }
  gert::StorageFormat fmt(ge::FORMAT_ND, ge::FORMAT_ND, {});
  std::string tp = TPrefix(index_);
  std::cout << tp << "[GE INPUT] item[" << index << "] name=" << ori_name
            << " | shape=" << ShapeToStr(shape) << " | size=" << data->GetSize()
            << " B | placement=host" << std::endl;
  inputs_.emplace_back(storage, fmt, gert::kOnHost, input_dtype, data->GetData());
  return SUCCESS;
}

Result InferenceAcl::HandleOutputs(std::vector<gert::Tensor> &outs, bool persist) {
  if (!persist) return SUCCESS;
  if (outs.size() != io_.outputs.size()) {
    LogError("HandleOutputs", "outputs", static_cast<long>(outs.size()),
             "returned output count mismatch with io_config");
    return FAILED;
  }
  std::vector<json> shapes;
  for (size_t i = 0; i < outs.size(); i++) {
    const OutputCfg &cfg = io_.outputs[i];
    gert::Shape s = outs[i].GetShape().GetShape();
    std::vector<int64_t> dims;
    int64_t numel = 1;
    for (int32_t d = 0; d < s.GetDimNum(); d++) {
      dims.push_back(s.GetDim(d));
      numel *= s.GetDim(d);
    }
    if (numel < 0) {
      LogError("HandleOutputs", cfg.name, numel, "negative runtime output shape");
      return FAILED;
    }
    // io_config output shape is a hint only (-1 = dynamic); the runtime shape from GE wins.
    if (!cfg.shape.empty() && cfg.shape.size() == dims.size()) {
      bool mismatch = false;
      for (size_t k = 0; k < dims.size(); k++) {
        if (cfg.shape[k] != -1 && cfg.shape[k] != dims[k]) { mismatch = true; break; }
      }
      if (mismatch) {
        std::cout << TPrefix(index_) << "[GE OUTPUT][WARN] out[" << i << "] " << cfg.name
                  << " config shape=" << ShapeToStr(cfg.shape)
                  << " != runtime shape=" << ShapeToStr(dims)
                  << "; using the runtime shape" << std::endl;
      }
    }
    size_t nbytes = static_cast<size_t>(numel) * cfg.elem_bytes;
    std::vector<uint8_t> host(nbytes);
    void *addr = outs[i].GetAddr();
    if (nbytes > 0 && addr == nullptr) {
      LogError("HandleOutputs", cfg.name, 0, "output address is null");
      return FAILED;
    }
    if (gert::TensorPlacementUtils::IsOnHost(outs[i].GetPlacement())) {
      if (nbytes > 0) std::memcpy(host.data(), addr, nbytes);
    } else {
      aclError e = aclrtMemcpy(host.data(), nbytes, addr, nbytes, ACL_MEMCPY_DEVICE_TO_HOST);
      if (e != ACL_SUCCESS) {
        LogError("HandleOutputs", cfg.name, static_cast<long>(e), "D2H memcpy failed");
        return FAILED;
      }
    }

    const std::string path = output_dir_ + "/output_" + std::to_string(i) + ".bin";
    const std::string tmp_path = path + ".tmp";
    FILE *fw = fopen(tmp_path.c_str(), "wb");
    if (fw == nullptr) {
      LogError("HandleOutputs", path, 0, "open output file failed");
      return FAILED;
    }
    const size_t written = fwrite(host.data(), 1, nbytes, fw);
    const int close_rc = fclose(fw);
    if (written != nbytes || close_rc != 0) {
      std::remove(tmp_path.c_str());
      LogError("HandleOutputs", path, static_cast<long>(written),
               "write output file failed");
      return FAILED;
    }
    if (std::rename(tmp_path.c_str(), path.c_str()) != 0) {
      std::remove(tmp_path.c_str());
      LogError("HandleOutputs", path, 0, "rename output file failed");
      return FAILED;
    }
    std::cout << TPrefix(index_) << "[GE OUTPUT] out[" << i << "] " << cfg.name << " | "
              << cfg.dtype << " | " << ShapeToStr(dims) << " | " << nbytes << " B saved"
              << std::endl;
    json item;
    item["index"] = cfg.index;
    item["name"] = cfg.name;
    item["shape"] = dims;
    shapes.push_back(item);
  }

  json root;
  root["outputs"] = shapes;
  const std::string shapes_path = output_dir_ + "/output_shapes.json";
  const std::string shapes_tmp = shapes_path + ".tmp";
  {
    std::ofstream of(shapes_tmp);
    if (!of.is_open()) {
      LogError("HandleOutputs", shapes_path, 0, "open output_shapes.json failed");
      return FAILED;
    }
    of << root.dump(2) << std::endl;
    of.flush();
    if (!of) {
      LogError("HandleOutputs", shapes_path, 0, "write output_shapes.json failed");
      return FAILED;
    }
  }
  if (std::rename(shapes_tmp.c_str(), shapes_path.c_str()) != 0) {
    std::remove(shapes_tmp.c_str());
    LogError("HandleOutputs", shapes_path, 0, "rename output_shapes.json failed");
    return FAILED;
  }

  // Completion marker is written last and atomically; verify.py only accepts outputs
  // carrying this marker (and optionally the matching GE_RUN_ID).
  const std::string complete_path = output_dir_ + "/.complete";
  const std::string complete_tmp = complete_path + ".tmp";
  {
    std::ofstream cf(complete_tmp);
    if (!cf.is_open()) {
      LogError("HandleOutputs", complete_path, 0, "open .complete failed");
      return FAILED;
    }
    cf << "run_id=" << GetEnv("GE_RUN_ID", "") << "\n"
       << "model_id=" << io_.model_id << "\n"
       << "output_count=" << outs.size() << "\n"
       << "finished_at=" << NowString() << "\n";
    cf.flush();
    if (!cf) {
      LogError("HandleOutputs", complete_path, 0, "write .complete failed");
      return FAILED;
    }
  }
  if (std::rename(complete_tmp.c_str(), complete_path.c_str()) != 0) {
    std::remove(complete_tmp.c_str());
    LogError("HandleOutputs", complete_path, 0, "rename .complete failed");
    return FAILED;
  }
  return SUCCESS;
}

void InferenceAcl::DestroyInput() {
  inputs_.clear();
  input_host_data_.clear();
}

Result InferenceAcl::Warmup() {
  // Trigger graph compilation with one RunGraphAsync that is excluded from statistics.
  // First-time graph compilation can legitimately take a long time, so warmup has a
  // larger timeout than the per-iteration execution timeout.
  const int timeout_sec = WarmupTimeoutSec();
  auto d = std::make_shared<std::promise<ge::Status>>();
  auto f = d->get_future();
  auto lifetime = std::make_shared<RunLifetime>();
  lifetime->Add();
  ge::Status enq = sess_->RunGraphAsync(graph_id_, inputs_,
                                        [d, lifetime](ge::Status st, std::vector<gert::Tensor> &) {
                                          lifetime->Done();
                                          d->set_value(st);
                                        });
  if (enq != ge::SUCCESS) {
    lifetime->Done();
    LogError("Warmup", "RunGraphAsync", enq, "warmup enqueue failed");
    stats_->Abort("warmup enqueue failed");
    return FAILED;
  }
  if (f.wait_for(std::chrono::seconds(timeout_sec)) != std::future_status::ready) {
    lifetime->timed_out.store(true);
    std::ostringstream msg;
    msg << "warmup RunGraphAsync did not complete within " << timeout_sec << "s";
    LogError("Warmup", "RunGraphAsync", 0,
             msg.str() +
                 "; first-time graph compilation may still be running; "
                 "this is a warmup-stage timeout, not an output/accuracy failure");
    stats_->Abort("warmup timeout");
    if (!lifetime->WaitZero(TimeoutGraceSec())) {
      std::ostringstream detail;
      detail << "timeout=" << timeout_sec << "s pending_callbacks=" << lifetime->pending.load()
             << "; warmup callback still in flight; this is a warmup-stage timeout, not an "
                "output/accuracy failure; exiting without destructors to avoid UAF";
      HardExitTimeout(index_, "Warmup", detail.str());
    }
    return FAILED;
  }
  if (f.get() != ge::SUCCESS) {
    LogError("Warmup", "RunGraphAsync", 0, "warmup execution failed");
    stats_->Abort("warmup execution failed");
    return FAILED;
  }
  return SUCCESS;
}

Result InferenceAcl::SyncStart() {
  // Barrier: all worker threads start the benchmark loop together. A thread that
  // fails before the barrier calls RunStats::Abort(), which wakes waiters instead
  // of leaving them blocked forever.
  std::unique_lock<std::mutex> lock(stats_->mu);
  if (stats_->aborted) return FAILED;
  ++stats_->ready;
  if (stats_->ready == stats_->expected_threads) {
    auto now = std::chrono::high_resolution_clock::now();
    stats_->start_time = now;
    stats_->before_us = getCurrentTimeStampInUs();
    stats_->use_time_total = 0;
    stats_->total_count = 0;
    stats_->min_heap99 = std::priority_queue<int64_t, std::vector<int64_t>, std::greater<int64_t>>();
    stats_->min_heap999 = std::priority_queue<int64_t, std::vector<int64_t>, std::greater<int64_t>>();
    stats_->barrier_passed = true;
    stats_->cv.notify_all();
  } else {
    stats_->cv.wait(lock, [this] {
      return stats_->barrier_passed || stats_->aborted ||
             (stop_ != nullptr && stop_->load());
    });
  }
  if (stats_->aborted || (stop_ != nullptr && stop_->load())) return FAILED;
  return SUCCESS;
}

void InferenceAcl::Pace() {
  // Global request rate limit shared by all threads (MaxQPS is aggregate).
  std::lock_guard<std::mutex> lock(stats_->mu);
  uint64_t cur_us = getCurrentTimeStampInUs();
  if (cur_us < stats_->before_us + stats_->task_interval_us) {
    std::this_thread::sleep_for(
        std::chrono::microseconds(stats_->before_us + stats_->task_interval_us - cur_us));
    stats_->before_us += stats_->task_interval_us;
  } else {
    stats_->before_us = cur_us;
  }
}

Result InferenceAcl::RunOnce(bool persist) {
  auto record_time = std::chrono::high_resolution_clock::now();
  auto done = std::make_shared<std::promise<ge::Status>>();
  auto fut = done->get_future();
  auto lifetime = std::make_shared<RunLifetime>();
  auto self = shared_from_this();
  const int timeout_sec = RunTimeoutSec();
  lifetime->Add();
  ge::Status enq = sess_->RunGraphAsync(
      graph_id_, inputs_,
      [self, lifetime, done, persist](ge::Status st, std::vector<gert::Tensor> &outs) {
        ge::Status out_st = st;
        if (st == ge::SUCCESS && persist && !lifetime->timed_out.load()) {
          out_st = self->HandleOutputs(outs, true);
        }
        lifetime->Done();
        done->set_value(out_st);
      });
  if (enq != ge::SUCCESS) {
    lifetime->Done();
    LogError("RunOnce", "RunGraphAsync", enq, "enqueue failed");
    stats_->Abort("execution enqueue failed");
    return FAILED;
  }
  if (fut.wait_for(std::chrono::seconds(timeout_sec)) != std::future_status::ready) {
    lifetime->timed_out.store(true);
    std::ostringstream msg;
    msg << "graph execution did not complete within " << timeout_sec << "s"
        << "; this is an execution timeout, not a warmup timeout";
    LogError("RunOnce", "RunGraphAsync", 0, msg.str());
    stats_->Abort("execution timeout");
    if (!lifetime->WaitZero(TimeoutGraceSec())) {
      std::ostringstream detail;
      detail << "timeout=" << timeout_sec << "s pending_callbacks=" << lifetime->pending.load()
             << "; execution callback still in flight; exiting without destructors to avoid UAF";
      HardExitTimeout(index_, "RunOnce", detail.str());
    }
    return FAILED;
  }
  if (fut.get() != ge::SUCCESS) {
    LogError("RunOnce", "RunGraphAsync", 0, "execution failed");
    stats_->Abort("execution failed");
    return FAILED;
  }

  auto end = std::chrono::high_resolution_clock::now();
  auto use_time = std::chrono::duration_cast<std::chrono::microseconds>(end - record_time);
  stats_->use_time_total += use_time.count();
  int64_t new_count = stats_->total_count.fetch_add(1) + 1;

  const size_t size99 = std::max<size_t>(1, stats_->debug_freq / 100);
  const size_t size999 = std::max<size_t>(1, stats_->debug_freq / 1000);
  std::lock_guard<std::mutex> lock(stats_->mu);
  push_if(stats_->min_heap99, size99, use_time.count());
  push_if(stats_->min_heap999, size999, use_time.count());
  if (new_count % stats_->debug_freq == 0) {
    auto now = std::chrono::high_resolution_clock::now();
    auto win_us =
        std::chrono::duration_cast<std::chrono::microseconds>(now - stats_->start_time).count();
    stats_->start_time = now;
    double qps = win_us > 0 ? (stats_->debug_freq * 1e6 / win_us) : 0.0;
    std::cout << TPrefix(index_) << "[GE PROGRESS] iter=" << new_count << "/"
              << stats_->total_iters
              << " | Qps=" << std::fixed << std::setprecision(2) << qps
              << std::setprecision(3)
              << " | avg session run time=" << stats_->use_time_total / 1e3 / stats_->debug_freq
              << "ms"
              << " | TP99:" << stats_->min_heap99.top() / 1e3 << "ms"
              << " | TP999:" << stats_->min_heap999.top() / 1e3 << "ms" << std::endl;
    stats_->use_time_total = 0;
    stats_->min_heap99 = std::priority_queue<int64_t, std::vector<int64_t>, std::greater<int64_t>>();
    stats_->min_heap999 = std::priority_queue<int64_t, std::vector<int64_t>, std::greater<int64_t>>();
  }
  return SUCCESS;
}

Result InferenceAcl::Execute() {
  std::string tp = TPrefix(index_);
  // Invalidate the previous run's completion marker as soon as this run starts.
  // A failed run must never leave a verifiable stale marker behind.
  std::remove((output_dir_ + "/.complete").c_str());
  std::remove((output_dir_ + "/.complete.tmp").c_str());
  if (aclrtSetDevice(device_id_) != ACL_SUCCESS) {
    LogError("Execute", "aclrtSetDevice", device_id_, "set device failed");
    stats_->Abort("set device failed");
    return FAILED;
  }
  device_set_ = true;
  if (ParseInput() != SUCCESS) {
    stats_->Abort("parse input failed");
    return FAILED;
  }
  if (Warmup() != SUCCESS) return FAILED;

  std::cout << tp << "[GE RUN] start (CircleCount=" << stats_->circle
            << ", threads=" << stats_->expected_threads
            << ", DebugFreq=" << stats_->debug_freq << ", placement=host)" << std::endl;

  if (SyncStart() != SUCCESS) {
    stats_->Abort("start barrier aborted");
    return FAILED;
  }

  const bool print_output = GetEnvBool("PrintOutput", false);
  for (int i = 0; i < stats_->circle; i++) {
    if (stop_ != nullptr && stop_->load()) {
      std::cout << tp << "[GE RUN] stop flag set, aborting loop" << std::endl;
      stats_->Abort("stop flag set");
      return FAILED;
    }
    Pace();
    const bool persist = print_output && (stats_->expected_threads == 1) &&
                         (i == stats_->circle - 1);
    if (RunOnce(persist) != SUCCESS) return FAILED;
  }
  std::cout << tp << "[GE RUN] done" << std::endl;
  return SUCCESS;
}