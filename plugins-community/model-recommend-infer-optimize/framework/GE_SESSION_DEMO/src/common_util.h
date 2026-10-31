#ifndef GE_SESSION_DEMO_COMMON_UTIL_H
#define GE_SESSION_DEMO_COMMON_UTIL_H

#include <cstddef>
#include <cstdint>
#include <functional>
#include <initializer_list>
#include <queue>
#include <string>
#include <vector>

#include "nlohmann/json.hpp"

using json = nlohmann::json;

// Environment variable helpers
std::string GetEnv(const char *key, const std::string &def);
bool GetEnvBool(const char *key, bool def);
// Strictly parse an int env var: default when missing, false when malformed
bool ParseEnvInt(const char *key, int64_t def, int64_t &out);

// Required JSON field check
bool JsonHas(const json &j, std::initializer_list<const char *> keys);

// Thread tag [T<id>] (shown when multi-thread)
bool ShowThreadPrefix();
std::string TPrefix(uint32_t index);

// shape -> [d0,d1,...]
std::string ShapeToStr(const std::vector<int64_t> &dims);

// Benchmark statistics helpers
void push_if(std::priority_queue<int64_t, std::vector<int64_t>, std::greater<int64_t>> &minHeap,
             size_t max_size, int64_t value);
uint64_t getCurrentTimeStampInUs();

#endif  // GE_SESSION_DEMO_COMMON_UTIL_H
