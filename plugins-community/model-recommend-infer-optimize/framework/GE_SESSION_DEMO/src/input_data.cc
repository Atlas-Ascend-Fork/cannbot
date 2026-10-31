#include "input_data.h"

#include <algorithm>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>

namespace {

// Owns aclrtMallocHost memory until the InputData object is fully constructed.
class HostBuffer {
 public:
  explicit HostBuffer(size_t bytes) {
    aclError err = aclrtMallocHost(&ptr_, bytes);
    if (err != ACL_SUCCESS || ptr_ == nullptr) {
      if (ptr_ != nullptr) aclrtFreeHost(ptr_);
      ptr_ = nullptr;
      throw std::runtime_error("Memory allocation failed");
    }
  }

  ~HostBuffer() {
    if (ptr_ != nullptr) aclrtFreeHost(ptr_);
  }

  HostBuffer(const HostBuffer &) = delete;
  HostBuffer &operator=(const HostBuffer &) = delete;

  void *get() const { return ptr_; }

  void *release() {
    void *p = ptr_;
    ptr_ = nullptr;
    return p;
  }

 private:
  void *ptr_ = nullptr;
};

}  // namespace

template <typename T>
InputData<T>::InputData(json &j) {
  if (j.is_number()) {
    size_t index = 0U;
    HostBuffer buffer(sizeof(T));
    T *data_ptr = static_cast<T *>(buffer.get());
    ParseInput(j, data_ptr, 1, index);
    size_ = sizeof(T);
    data_ = buffer.release();
    return;
  }
  if (!j.is_array()) {
    throw std::invalid_argument("only support array or number format json data");
  }
  size_t index = 0U;
  size_t input_size = GetInputSize(j);
  size_ = input_size * sizeof(T);
  if (size_ == 0) throw std::runtime_error("Input size is wrong");
  HostBuffer buffer(size_);
  T *data_ptr = static_cast<T *>(buffer.get());
  ParseInput(j, data_ptr, input_size, index);
  data_ = buffer.release();
}

template <typename T>
InputData<T>::InputData(json &j, size_t rows, size_t ori_rows) {
  if (!j.is_array()) {
    throw std::invalid_argument("only support array format json data");
  }
  if (ori_rows == 0) {
    throw std::invalid_argument("ori_rows must be > 0");
  }
  if (rows < ori_rows) {
    throw std::invalid_argument("rows must be >= ori_rows");
  }
  size_t index = 0U;
  size_t input_size = GetInputSize(j);
  size_ = input_size / ori_rows * rows * sizeof(T);
  HostBuffer buffer(size_);
  T *data_ptr = static_cast<T *>(buffer.get());
  ParseInput(j, data_ptr, size_ / sizeof(T), index);
  size_t remaining_rows = rows - ori_rows;
  size_t row_offsets = input_size / ori_rows;
  T *src = data_ptr;
  T *dest = src + ori_rows * row_offsets;
  int32_t rows_left = static_cast<int32_t>(remaining_rows);
  while (rows_left > 0) {
    int32_t rows_copy = std::min(rows_left, static_cast<int32_t>(ori_rows));
    size_t copy_data = rows_copy * row_offsets;
    size_t copy_bytes = copy_data * sizeof(T);
    aclError err = aclrtMemcpy(dest, copy_bytes, src, copy_bytes, ACL_MEMCPY_HOST_TO_HOST);
    if (err != ACL_SUCCESS) throw std::runtime_error("Memcopy failed");
    dest += copy_data;
    rows_left -= ori_rows;
  }
  data_ = buffer.release();
}

template <typename T>
size_t InputData<T>::GetInputSize(json &j) {
  size_t count = 0;
  if (j.is_array()) {
    for (auto &el : j) count += GetInputSize(el);
  } else {
    count = 1;
  }
  return count;
}

template <typename T>
void *InputData<T>::ParseInput(json &j, T *data_ptr, const size_t &limits_size, size_t &index) {
  if (j.is_array()) {
    for (auto &el : j) {
      if (index < limits_size) ParseInput(el, data_ptr, limits_size, index);
    }
  } else {
    data_ptr[index] = j.get<T>();
    index++;
  }
  return nullptr;
}

template <typename T>
InputData<T>::~InputData() {
  if (data_ != nullptr) aclrtFreeHost(data_);
}

template <typename T>
void *InputData<T>::GetData() {
  return data_;
}

template <typename T>
size_t InputData<T>::GetSize() {
  return size_;
}

// Explicit instantiation
template class InputData<int64_t>;
template class InputData<int32_t>;
template class InputData<uint8_t>;
template class InputData<uint16_t>;
template class InputData<float>;