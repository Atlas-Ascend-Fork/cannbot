#ifndef GE_SESSION_DEMO_INPUT_DATA_H
#define GE_SESSION_DEMO_INPUT_DATA_H

#include <cstddef>
#include <string>

#include "acl/acl.h"
#include "nlohmann/json.hpp"

using json = nlohmann::json;

// Input data base class / template (definitions and explicit instantiation in input_data.cc)
class InputDataBase {
 public:
  virtual ~InputDataBase() = default;
  virtual void *GetData() = 0;
  virtual size_t GetSize() = 0;
};

template <typename T>
class InputData : public InputDataBase {
 public:
  explicit InputData(json &j);
  explicit InputData(json &j, size_t rows, size_t ori_rows);
  ~InputData() override;
  static size_t GetInputSize(json &j);
  static void *ParseInput(json &j, T *data_ptr, const size_t &limit_size, size_t &index);
  void *GetData() override;
  size_t GetSize() override;

 private:
  void *data_ = nullptr;
  size_t size_ = 0;
};

extern template class InputData<int64_t>;
extern template class InputData<int32_t>;
extern template class InputData<uint8_t>;
extern template class InputData<uint16_t>;
extern template class InputData<float>;

#endif  // GE_SESSION_DEMO_INPUT_DATA_H
