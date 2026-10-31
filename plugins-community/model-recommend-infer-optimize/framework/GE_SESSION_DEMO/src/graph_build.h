#ifndef GE_SESSION_DEMO_GRAPH_BUILD_H
#define GE_SESSION_DEMO_GRAPH_BUILD_H

#include <map>
#include <string>

#include "ge/ge_api.h"
#include "io_config.h"

// Parse ge::Graph from io_config and the model file, and build AddGraph options (hints).
// Returns false when parsing fails.
bool BuildGraph(const IoConfig &io, const std::string &model_path, ge::Graph &graph,
                std::map<ge::AscendString, ge::AscendString> &graph_options);

#endif  // GE_SESSION_DEMO_GRAPH_BUILD_H
