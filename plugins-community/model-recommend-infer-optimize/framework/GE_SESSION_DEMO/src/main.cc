// GE_SESSION_DEMO entry point: GE v2 (GeSession + RunGraphAsync) config-driven inference.
// Single GeSession + single Graph, AddGraph repeated on the same graph_id (once per concurrency slot).

#include <atomic>
#include <cctype>
#include <chrono>
#include <condition_variable>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "acl/acl.h"
#include "ge/ge_api.h"
#include "ge/ge_api_v2.h"
#include "graph/ascend_string.h"

#include "graph_build.h"
#include "inference_acl.h"
#include "io_config.h"

static constexpr int kExitFail = -1;
static constexpr int kExitOk = 0;
static constexpr uint32_t kGraphId = 0;  // single graph, same graph_id

static std::string ResolvePath(const std::string &root, const std::string &p) {
  if (p.empty()) return p;
  if (p[0] == '/') return p;
  return root + "/" + p;
}

int main() {
  std::cout << "============================================================\n"
            << " GE_SESSION_DEMO - GE Session inference (RunGraphAsync)\n"
            << "============================================================" << std::endl;

  std::string root = GetEnv("GE_DEMO_ROOT", ".");
  std::string model_id = GetEnv("MODEL_ID", "");
  if (model_id.empty()) {
    std::cout << "[ERROR] MODEL_ID is required (e.g. 001)" << std::endl;
    return kExitFail;
  }
  if (model_id[0] == 'M' || model_id[0] == 'm') model_id = model_id.substr(1);
  for (char c : model_id) {
    if (!(std::isalnum(static_cast<unsigned char>(c)) || c == '_')) {
      std::cout << "[ERROR] invalid MODEL_ID: " << model_id << std::endl;
      return kExitFail;
    }
  }

  std::string io_path = root + "/models/M" + model_id + "/config/io_config.json";

  std::cout << "[GE PHASE 1/5] load configuration" << std::endl;
  IoConfig io;
  try {
    io = IoConfig::Load(io_path);
  } catch (const std::exception &e) {
    std::cout << "[ERROR] failed to load io_config: " << e.what() << std::endl;
    return kExitFail;
  }
  io.model_file = ResolvePath(root, io.model_file);
  io.batch_list = ResolvePath(root, io.batch_list);
  io.output_dir = ResolvePath(root, io.output_dir.empty() ? ("models/M" + model_id + "/output") : io.output_dir);
  std::cout << "  model id       : " << io.model_id << std::endl;
  std::cout << "  model file     : " << io.model_file << std::endl;
  std::cout << "  input list     : " << io.batch_list << std::endl;
  std::cout << "  output dir     : " << io.output_dir << std::endl;
  std::cout << "  framework      : " << io.framework << std::endl;
  std::cout << "  batch/strategy : " << io.batch_size << " / " << io.shape_mode
            << " (pass_input_shape=" << (io.pass_input_shape ? "true" : "false") << ")" << std::endl;
  std::cout << "  inputs/outputs : " << io.inputs.size() << " / " << io.outputs.size() << std::endl;

  std::string core_num_str = GetEnv("CORE_NUM", "24|48");
  std::string hf32_env = GetEnv("ENABLE_HF32", "False");
  std::string allow_hf32 = "0";
  if (hf32_env == "True" || hf32_env == "true") {
    allow_hf32 = "1";
  } else if (hf32_env != "False" && hf32_env != "false") {
    allow_hf32 = hf32_env;  // raw 2-bit value: "01"=MatMul only, "10"=Conv only, "11"=both
  }
  std::string force_16 = GetEnv("FORCE_16", "False") == "True" ? "1" : "0";
  std::string graph_max_parallel = GetEnv("GRAPH_MAX_PARALLEL", "8");

  std::map<ge::AscendString, ge::AscendString> ge_init;
  ge_init[ge::AscendString("ge.exec.deviceId")] = ge::AscendString(GetEnv("GE_DEVICE_ID", "0").c_str());
  if (allow_hf32 == "0" || allow_hf32 == "00") {
    ge_init[ge::AscendString("ge.exec.precision_mode")] =
        ge::AscendString(force_16 == "1" ? "force_fp16" : "must_keep_origin_dtype");
  }
  ge_init[ge::AscendString("ge.exec.allow_hf32")] = ge::AscendString(allow_hf32.c_str());
  ge_init[ge::AscendString("ge.aicoreNum")] = ge::AscendString(core_num_str.c_str());
  ge_init[ge::AscendString("ge.graphMaxParallelModelNum")] = ge::AscendString(graph_max_parallel.c_str());
  ge_init[ge::AscendString("ge.inputBatchCpy")] = ge::AscendString("1");
  std::string op_precision = GetEnv("GE_OP_PRECISION_MODE", "");
  if (!op_precision.empty())
    ge_init[ge::AscendString("ge.exec.op_precision_mode")] = ge::AscendString(op_precision.c_str());
  std::string fusion_file = GetEnv("GE_FUSION_SWITCH_FILE", "");
  if (!fusion_file.empty())
    ge_init[ge::AscendString("ge.fusionSwitchFile")] = ge::AscendString(fusion_file.c_str());

  std::cout << "\n[GE PHASE 2/5] initialize GE(V2) / ACL" << std::endl;
  std::cout << "  cores          : " << core_num_str << std::endl;
  std::cout << "  precision      : " << (force_16 == "1" ? "force_fp16" : "must_keep_origin_dtype")
            << " (allow_hf32=" << allow_hf32 << ")" << std::endl;
  std::cout << "  graphMaxParallel: " << graph_max_parallel << std::endl;
  ge::Status ret = ge::GEInitializeV2(ge_init);
  if (ret != ge::SUCCESS) {
    std::cout << "[ERROR] GEInitializeV2 failed, code=" << ret << std::endl;
    return kExitFail;
  }
  std::cout << "  GE init        : ok" << std::endl;

  aclError acl_ret = aclInit(nullptr);
  if (acl_ret != ACL_ERROR_NONE) {
    std::cout << "[ERROR] ACL init failed, code=" << acl_ret << std::endl;
    ge::GEFinalizeV2();
    return kExitFail;
  }
  std::cout << "  ACL init       : ok" << std::endl;

  int64_t device_num_v = 1, start_device_v = 0, thread_num_v = 1;
  if (!ParseEnvInt("DEVICE_NUM", 1, device_num_v) || device_num_v != 1) {
    std::cout << "[ERROR] DEVICE_NUM must be 1 (multi-device is not supported)" << std::endl;
    ge::GEFinalizeV2();
    aclFinalize();
    return kExitFail;
  }
  if (!ParseEnvInt("START_DEVICE", 0, start_device_v) || start_device_v < 0) {
    std::cout << "[ERROR] invalid START_DEVICE (must be >= 0)" << std::endl;
    ge::GEFinalizeV2();
    aclFinalize();
    return kExitFail;
  }
  if (!ParseEnvInt("THREAD_NUM", 1, thread_num_v) || thread_num_v < 1) {
    std::cout << "[ERROR] invalid THREAD_NUM (must be >= 1)" << std::endl;
    ge::GEFinalizeV2();
    aclFinalize();
    return kExitFail;
  }
  int device_num = static_cast<int>(device_num_v);
  int start_device = static_cast<int>(start_device_v);
  int thread_num = static_cast<int>(thread_num_v);

  int64_t total_die_v = 16;
  if (!ParseEnvInt("TOTAL_DIE", 16, total_die_v) || total_die_v < 1) {
    std::cout << "[ERROR] invalid TOTAL_DIE (must be >= 1)" << std::endl;
    ge::GEFinalizeV2();
    aclFinalize();
    return kExitFail;
  }

  int64_t circle_v = 1, max_qps_v = 20000, debug_freq_v = 1000;
  if (!ParseEnvInt("CircleCount", 1, circle_v) || circle_v < 1 ||
      !ParseEnvInt("MaxQPS", 20000, max_qps_v) || max_qps_v < 1 ||
      !ParseEnvInt("DebugFreq", 1000, debug_freq_v) || debug_freq_v < 1) {
    std::cout << "[ERROR] invalid CircleCount/MaxQPS/DebugFreq" << std::endl;
    ge::GEFinalizeV2();
    aclFinalize();
    return kExitFail;
  }

  std::cout << "\n[GE PHASE 3/5] create session(s) and add graph" << std::endl;
  std::cout << "  devices        : " << device_num << " (start die " << start_device
            << "), threads/device " << thread_num << std::endl;

  std::atomic<bool> stop{false};
  std::atomic<bool> failed{false};

  std::vector<std::unique_ptr<ge::GeSession>> sessions;
  std::vector<std::unique_ptr<std::thread>> threads;
  std::vector<std::shared_ptr<RunStats>> all_stats;

  // Failure path: stop and join workers before releasing sessions, then finalize
  // GE/ACL in the same order as the successful path.
  auto abort_cleanup = [&](std::unique_ptr<ge::GeSession> &current_session) {
    stop.store(true);
    for (auto &s : all_stats) s->Abort("main stop requested");
    for (auto &t : threads) {
      if (t && t->joinable()) t->join();
    }
    threads.clear();
    if (current_session) current_session.reset();
    sessions.clear();
    ge::GEFinalizeV2();
    aclFinalize();
  };

  for (int i = 0; i < device_num; i++) {
    std::map<ge::AscendString, ge::AscendString> sess_opts;
    int cur_dev = static_cast<int>((start_device + i) % total_die_v);
    sess_opts[ge::AscendString("ge.session_device_id")] = ge::AscendString(std::to_string(cur_dev).c_str());
    sess_opts[ge::AscendString("ge.constLifecycle")] = ge::AscendString("session");
    sess_opts[ge::AscendString("ge.exec.allTensorNotEmpty")] = ge::AscendString("1");
    if (GetEnv("DumpData", "false") == "true") {
      sess_opts[ge::AscendString("ge.exec.enableDump")] = ge::AscendString("1");
      sess_opts[ge::AscendString("ge.exec.dumpPath")] = ge::AscendString(GetEnv("GE_DUMP_PATH", "./dump_data").c_str());
      sess_opts[ge::AscendString("ge.exec.dumpMode")] = ge::AscendString("all");
    }
    auto session = std::make_unique<ge::GeSession>(sess_opts);
    std::cout << "  device " << cur_dev << "       : session created" << std::endl;

    ge::Graph graph;
    std::map<ge::AscendString, ge::AscendString> graph_options;
    if (!BuildGraph(io, io.model_file, graph, graph_options)) {
      std::cout << "[ERROR] build graph failed" << std::endl;
      abort_cleanup(session);
      return kExitFail;
    }
    for (int t = 0; t < thread_num; t++) {
      ge::Status s = session->AddGraph(kGraphId, graph, graph_options);
      if (s != ge::SUCCESS) {
        std::cout << "[ERROR] AddGraph #" << (t + 1) << " failed, code=" << s << std::endl;
        abort_cleanup(session);
        return kExitFail;
      }
    }
    std::cout << "  graph_id " << kGraphId << "     : AddGraph x" << thread_num << " ok" << std::endl;

    // Per-device shared run statistics, owned here for the whole thread lifetime.
    auto stats = std::make_shared<RunStats>();
    stats->expected_threads = thread_num;
    stats->circle = static_cast<int>(circle_v);
    stats->debug_freq = static_cast<int>(debug_freq_v);
    stats->task_interval_us = 1000000ull / static_cast<uint64_t>(max_qps_v);
    stats->total_iters = circle_v * thread_num;
    all_stats.push_back(stats);

    ge::GeSession *sess_ptr = session.get();
    sessions.push_back(std::move(session));

    if (i == 0) std::cout << "\n[GE PHASE 4/5] start inference threads" << std::endl;
    for (int j = 0; j < thread_num; j++) {
      int index = i * thread_num + j;
      std::string tag = ShowThreadPrefix() ? ("[T" + std::to_string(index) + "]")
                                           : std::to_string(index);
      std::cout << "  device " << cur_dev << "       : thread " << tag << " started" << std::endl;
      threads.emplace_back(std::make_unique<std::thread>(
          [sess_ptr, index, cur_dev, &io, stats, &stop, &failed]() {
            auto infer = std::make_shared<InferenceAcl>(
                io, sess_ptr, kGraphId, index, static_cast<uint32_t>(cur_dev),
                stats.get(), &stop);
            if (infer->Execute() != SUCCESS) {
              failed.store(true);
              stop.store(true);
            }
          }));
    }
  }

  std::cout << "\n[GE PHASE 5/5] join and finalize" << std::endl;
  for (auto &t : threads) t->join();
  std::cout << "  threads        : all joined" << std::endl;

  sessions.clear();  // release sessions before GEFinalizeV2

  ret = ge::GEFinalizeV2();
  if (ret != ge::SUCCESS) {
    std::cout << "[ERROR] GEFinalizeV2 failed, code=" << ret << std::endl;
    return kExitFail;
  }
  std::cout << "  GE finalize    : ok" << std::endl;

  acl_ret = aclFinalize();
  if (acl_ret != ACL_ERROR_NONE) {
    std::cout << "[ERROR] ACL finalize failed, code=" << acl_ret << std::endl;
    return kExitFail;
  }
  std::cout << "  ACL finalize   : ok" << std::endl;

  if (failed.load()) {
    std::string reason;
    for (auto &s : all_stats) {
      const std::string r = s->FailureReason();
      if (!r.empty()) {
        reason = r;
        break;
      }
    }
    if (reason.empty()) reason = "unknown failure";
    std::cout << "\n[GE RESULT] inference failed: " << reason << std::endl;
    return kExitFail;
  }
  std::cout << "\n[GE RESULT] inference finished: success" << std::endl;
  return kExitOk;
}