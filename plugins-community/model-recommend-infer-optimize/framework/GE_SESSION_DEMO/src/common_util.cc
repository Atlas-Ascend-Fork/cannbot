#include "common_util.h"

#include <cctype>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

// ============================================================
// Helpers
// ============================================================

std::string GetEnv(const char *key, const std::string &def) {
  const char *v = getenv(key);
  return (v != nullptr) ? std::string(v) : def;
}

bool GetEnvBool(const char *key, bool def) {
  const char *v = getenv(key);
  if (v == nullptr) return def;
  std::string s(v);
  return !(s == "False" || s == "false" || s == "0" || s.empty());
}

// Show the thread tag only when running multiple threads; keep single-thread output clean
bool ShowThreadPrefix() {
  static const bool show = [] {
    int t = std::atoi(GetEnv("THREAD_NUM", "1").c_str());
    int d = std::atoi(GetEnv("DEVICE_NUM", "1").c_str());
    return (t > 1 || d > 1);
  }();
  return show;
}

// Required JSON field check
bool JsonHas(const json &j, std::initializer_list<const char *> keys) {
  for (const char *k : keys) {
    if (!j.contains(k)) return false;
  }
  return true;
}

// Thread tag: [T<id>] (empty string for a single thread)
std::string TPrefix(uint32_t index) {
  if (!ShowThreadPrefix()) return "";
  return "[T" + std::to_string(index) + "]";
}

// shape -> [d0,d1,...]
std::string ShapeToStr(const std::vector<int64_t> &dims) {
  std::string s = "[";
  for (size_t i = 0; i < dims.size(); i++) {
    s += std::to_string(dims[i]);
    if (i + 1 != dims.size()) s += ",";
  }
  return s + "]";
}


void push_if(std::priority_queue<int64_t, std::vector<int64_t>, std::greater<int64_t>> &minHeap,
             size_t max_size, int64_t value) {
  if (minHeap.size() < max_size) {
    minHeap.push(value);
  } else if (value > minHeap.top()) {
    minHeap.pop();
    minHeap.push(value);
  }
}

uint64_t getCurrentTimeStampInUs() {
  auto now = std::chrono::system_clock::now();
  auto us = std::chrono::duration_cast<std::chrono::microseconds>(now.time_since_epoch());
  return us.count();
}

// Strictly parse an int env var: default when missing, false when malformed
bool ParseEnvInt(const char *key, int64_t def, int64_t &out) {
  const char *v = getenv(key);
  if (v == nullptr) {
    out = def;
    return true;
  }
  std::string s(v);
  if (s.empty()) return false;
  size_t i = 0;
  if (s[0] == '+' || s[0] == '-') i = 1;
  if (i == s.size()) return false;
  for (; i < s.size(); ++i) {
    if (!std::isdigit(static_cast<unsigned char>(s[i]))) return false;
  }
  try {
    out = std::stoll(s);
  } catch (...) {
    return false;
  }
  return true;
}
