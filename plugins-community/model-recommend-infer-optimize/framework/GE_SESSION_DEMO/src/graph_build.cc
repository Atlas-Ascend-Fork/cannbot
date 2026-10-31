#include "graph_build.h"

#include <iostream>
#include <map>
#include <string>

#include "common_util.h"
#include "parser/onnx_parser.h"
#include "parser/tensorflow_parser.h"

static std::string JoinInputShape(const IoConfig &io) {
  std::string s;
  for (size_t i = 0; i < io.inputs.size(); i++) {
    s += io.inputs[i].name + ":" + io.inputs[i].parser_shape;
    if (i + 1 != io.inputs.size()) s += ";";
  }
  return s;
}

static std::string JoinOutputNodes(const IoConfig &io) {
  std::string s;
  for (size_t i = 0; i < io.outputs.size(); i++) {
    s += io.outputs[i].name;
    if (i + 1 != io.outputs.size()) s += ";";
  }
  return s;
}

static std::string JoinHintShape(const IoConfig &io) {
  std::string s;
  for (size_t i = 0; i < io.inputs.size(); i++) {
    if (io.inputs[i].hint_shape.empty()) continue;
    if (!s.empty()) s += ";";
    s += io.inputs[i].hint_shape;
  }
  return s;
}

static bool EndsWith(const std::string &s, const char *suffix) {
  std::string suf(suffix);
  return s.size() >= suf.size() && s.compare(s.size() - suf.size(), suf.size(), suf) == 0;
}

bool BuildGraph(const IoConfig &io, const std::string &model_path, ge::Graph &graph,
                std::map<ge::AscendString, ge::AscendString> &graph_options) {
  // Model format: prefer the framework hint, then the file suffix. This demo supports
  // onnx/tensorflow only; other formats are rejected; unknown is treated as onnx.
  // Extend the parse branch below if more formats are needed.
  std::string format;
  const std::string &fw = io.framework;
  if (fw == "tf" || fw == "tensorflow" || fw == "pb") {
    format = "tensorflow";
  } else if (fw == "onnx" || fw.empty()) {
    if (EndsWith(model_path, ".pb") || EndsWith(model_path, ".pbtxt")) {
      format = "tensorflow";
    } else if (EndsWith(model_path, ".prototxt") || EndsWith(model_path, ".caffemodel") ||
               EndsWith(model_path, ".air")) {
      std::cout << "[ERROR] unsupported model format: " << model_path
                << " (this demo supports onnx/tensorflow only)" << std::endl;
      return false;
    } else {
      format = "onnx";
    }
  } else {
    std::cout << "[ERROR] unsupported framework '" << fw
              << "' (this demo supports onnx/tensorflow only)" << std::endl;
    return false;
  }

  std::map<ge::AscendString, ge::AscendString> parser_params;
  if (io.pass_input_shape) {
    std::string in_shape = JoinInputShape(io);
    std::string out_nodes = JoinOutputNodes(io);
    std::string out_show = out_nodes.size() > 80 ? out_nodes.substr(0, 77) + "..." : out_nodes;
    std::cout << "[GE BUILD] format=" << format << " | inputs=" << io.inputs.size()
              << " | pass_input_shape=on | out_nodes=" << out_show << std::endl;
    parser_params[ge::AscendString(ge::ir_option::INPUT_SHAPE)] = ge::AscendString(in_shape.c_str());
    parser_params[ge::AscendString(ge::ir_option::OUT_NODES)] = ge::AscendString(out_nodes.c_str());
  } else {
    std::cout << "[GE BUILD] format=" << format
              << " | pass_input_shape=off (all_dynamic mode)" << std::endl;
  }

  ge::graphStatus r;
  if (format == "tensorflow") {
    r = ge::aclgrphParseTensorFlow(model_path.c_str(), parser_params, graph);
  } else {
    r = ge::aclgrphParseONNX(model_path.c_str(), parser_params, graph);
  }
  if (r != 0) {
    std::cout << "[ERROR] parse model failed, status=" << r << std::endl;
    return false;
  }

  std::string hint = JoinHintShape(io);
  if (!hint.empty()) {
    graph_options[ge::AscendString("ge.inputHintShape")] = ge::AscendString(hint.c_str());
  }
  return true;
}
