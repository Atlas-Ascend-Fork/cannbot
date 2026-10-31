#ifndef GE_SESSION_DEMO_INFERENCE_ACL_H
#define GE_SESSION_DEMO_INFERENCE_ACL_H

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <functional>
#include <iostream>
#include <memory>
#include <mutex>
#include <queue>
#include <string>
#include <vector>

#include "acl/acl.h"
#include "ge/ge_api.h"
#include "ge/ge_api_v2.h"

#include "common_util.h"
#include "input_data.h"
#include "io_config.h"

typedef enum Result {
  SUCCESS = 0,
  FAILED = 1
} Result;

#define IF_RESULT_ERROR(expr, interface) \
  do { \
    const auto __ret = (expr); \
    if (__ret != SUCCESS) { \
      std::cout << #interface " failed" << std::endl; \
      return FAILED; \
    } \
  } while (false)

// Run-wide shared statistics for all worker threads of one device.
// Owned by main() so its lifetime is independent from individual executors;
// this replaces process-wide function-local static state.
struct RunStats {
  std::mutex mu;
  std::condition_variable cv;
  int32_t expected_threads = 1;
  int32_t ready = 0;
  int32_t circle = 1;
  int32_t debug_freq = 1000;
  int64_t total_iters = 1;
  uint64_t task_interval_us = 1000;
  std::chrono::high_resolution_clock::time_point start_time =
      std::chrono::high_resolution_clock::now();
  std::priority_queue<int64_t, std::vector<int64_t>, std::greater<int64_t>> min_heap99;
  std::priority_queue<int64_t, std::vector<int64_t>, std::greater<int64_t>> min_heap999;
  uint64_t before_us = 0;
  std::atomic<int64_t> use_time_total{0};
  std::atomic<int64_t> total_count{0};
  bool aborted = false;
  bool barrier_passed = false;
  std::string abort_reason;

  // Wake every thread waiting at the start barrier and remember why the run failed.
  void Abort(const std::string &reason) {
    std::lock_guard<std::mutex> lock(mu);
    if (!aborted) {
      aborted = true;
      abort_reason = reason;
    }
    cv.notify_all();
  }

  std::string FailureReason() {
    std::lock_guard<std::mutex> lock(mu);
    return abort_reason;
  }
};

// Executor: runs RunGraphAsync concurrently on a shared GeSession and a fixed graph_id.
// The graph is parsed once by main() and added once per concurrency slot; this class
// only parses inputs and drives asynchronous execution.
class InferenceAcl : public std::enable_shared_from_this<InferenceAcl> {
 public:
  explicit InferenceAcl(const IoConfig &io, ge::GeSession *sess, uint32_t graph_id,
                        uint32_t index, uint32_t device_id, RunStats *stats,
                        std::atomic<bool> *stop);

  ~InferenceAcl();

  Result Execute();

 private:
  void LogError(const std::string &stage, const std::string &obj, long ret,
                const std::string &reason);

  Result ParseInput();
  Result ParseInputJson();
  Result ParseSingleInput(const json &json_obj, uint32_t index);

  // Output handling: when persist is true, write output_i.bin and output_shapes.json.
  Result HandleOutputs(std::vector<gert::Tensor> &outs, bool persist);

  Result Warmup();
  Result SyncStart();
  void Pace();
  Result RunOnce(bool persist);

  void DestroyInput();

  IoConfig io_;
  ge::GeSession *sess_ = nullptr;
  uint32_t graph_id_ = 0;
  uint32_t index_ = 0;
  uint32_t device_id_ = 0;
  bool device_set_ = false;
  RunStats *stats_ = nullptr;
  std::atomic<bool> *stop_ = nullptr;
  std::string batch_list_path_;
  std::string output_dir_;
  json j_;
  std::vector<gert::Tensor> inputs_;
  std::vector<std::shared_ptr<InputDataBase>> input_host_data_;
  size_t total_size_ = 0;
};

#endif  // GE_SESSION_DEMO_INFERENCE_ACL_H