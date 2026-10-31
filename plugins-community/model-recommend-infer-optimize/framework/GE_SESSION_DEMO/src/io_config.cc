#include "io_config.h"

#include <fstream>
#include <iostream>
#include <string>
#include <vector>

#include "common_util.h"

// ============================================================
// Configuration loading
// ============================================================

IoConfig IoConfig::Load(const std::string &path) {
  std::ifstream f(path);
  if (!f.is_open()) {
    throw std::runtime_error("cannot open io_config: " + path);
  }
  json j;
  f >> j;
  IoConfig io;
  io.model_id = j.value("model_id", "");
  io.model_file = j.value("model_file", "");
  io.framework = j.value("framework", "onnx");
  io.batch_size = j.value("batch_size", 1);
  io.pass_input_shape = j.value("pass_input_shape", true);
  io.shape_mode = j.value("shape_mode", "all_static");
  io.batch_list = j.value("batch_list", "");
  io.output_dir = j.value("output_dir", "");
  for (const auto &e : j["inputs"]) {
    InputCfg c;
    c.name = e.value("name", "");
    c.parser_shape = e.value("parser_shape", "");
    c.hint_shape = e.value("hint_shape", "");
    io.inputs.push_back(std::move(c));
  }
  for (const auto &e : j["outputs"]) {
    OutputCfg c;
    c.index = e.value("index", 0);
    c.name = e.value("name", "");
    c.dtype = e.value("dtype", "float32");
    c.elem_bytes = e.value("elem_bytes", 4);
    if (e.contains("shape")) {
      for (const auto &d : e["shape"]) c.shape.push_back(d.get<int64_t>());
    }
    io.outputs.push_back(std::move(c));
  }
  return io;
}