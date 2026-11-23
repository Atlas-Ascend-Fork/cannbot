/*!
 * CANNBot portal adaptations:
 * Copyright (c) 2026 Huawei Technologies Co., Ltd.
 * This program is free software, you can redistribute it and/or modify it under the terms and conditions of
 * CANN Open Software License Agreement Version 2.0 (the "License").
 * Please refer to the License for details. You may not use this file except in compliance with the License.
 * THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND, EITHER EXPRESS OR IMPLIED,
 * INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT, MERCHANTABILITY, OR FITNESS FOR A PARTICULAR PURPOSE.
 * See LICENSE in the root of the software repository for the full text of the License.
 *
 * Source: https://cann.cannbot.cn/dsh-native-replay-v3/replay-transport-download.js
 * Bundled components retain their respective copyrights and licenses.
 */

(() => {
  // ../tmp/cannbot-native-replay/node_modules/@vitest/spy/dist/index.js
  function isMockFunction(fn2) {
    return typeof fn2 === "function" && "_isMockFunction" in fn2 && fn2._isMockFunction === true;
  }
  var MOCK_RESTORE = /* @__PURE__ */ new Set();
  var REGISTERED_MOCKS = /* @__PURE__ */ new Set();
  var MOCK_CONFIGS = /* @__PURE__ */ new WeakMap();
  function createMockInstance(options = {}) {
    const { originalImplementation, restore, mockImplementation, resetToMockImplementation, resetToMockName } = options;
    if (restore) {
      MOCK_RESTORE.add(restore);
    }
    const config = getDefaultConfig(originalImplementation);
    const state = getDefaultState();
    const mock = createMock({
      config,
      state,
      ...options
    });
    const mockLength = (mockImplementation || originalImplementation)?.length ?? 0;
    Object.defineProperty(mock, "length", {
      writable: true,
      enumerable: false,
      value: mockLength,
      configurable: true
    });
    if (resetToMockName) {
      config.mockName = mock.name || "vi.fn()";
    }
    MOCK_CONFIGS.set(mock, config);
    REGISTERED_MOCKS.add(mock);
    mock._isMockFunction = true;
    mock.getMockImplementation = () => {
      return config.onceMockImplementations[0] || config.mockImplementation;
    };
    Object.defineProperty(mock, "mock", {
      configurable: false,
      enumerable: true,
      writable: false,
      value: state
    });
    mock.mockImplementation = function mockImplementation2(implementation) {
      config.mockImplementation = implementation;
      return mock;
    };
    mock.mockImplementationOnce = function mockImplementationOnce(implementation) {
      config.onceMockImplementations.push(implementation);
      return mock;
    };
    mock.withImplementation = function withImplementation(implementation, callback) {
      const previousImplementation = config.mockImplementation;
      const previousOnceImplementations = config.onceMockImplementations;
      const reset = () => {
        config.mockImplementation = previousImplementation;
        config.onceMockImplementations = previousOnceImplementations;
      };
      config.mockImplementation = implementation;
      config.onceMockImplementations = [];
      const returnValue = callback();
      if (typeof returnValue === "object" && typeof returnValue?.then === "function") {
        return returnValue.then(() => {
          reset();
          return mock;
        });
      } else {
        reset();
      }
      return mock;
    };
    mock.mockReturnThis = function mockReturnThis() {
      return mock.mockImplementation(function() {
        return this;
      });
    };
    mock.mockReturnValue = function mockReturnValue(value) {
      return mock.mockImplementation(function() {
        if (new.target) {
          throwConstructorError("mockReturnValue");
        }
        return value;
      });
    };
    mock.mockReturnValueOnce = function mockReturnValueOnce(value) {
      return mock.mockImplementationOnce(function() {
        if (new.target) {
          throwConstructorError("mockReturnValueOnce");
        }
        return value;
      });
    };
    mock.mockThrow = function mockThrow(value) {
      return mock.mockImplementation(function() {
        throw value;
      });
    };
    mock.mockThrowOnce = function mockThrowOnce(value) {
      return mock.mockImplementationOnce(function() {
        throw value;
      });
    };
    mock.mockResolvedValue = function mockResolvedValue(value) {
      return mock.mockImplementation(function() {
        if (new.target) {
          throwConstructorError("mockResolvedValue");
        }
        return Promise.resolve(value);
      });
    };
    mock.mockResolvedValueOnce = function mockResolvedValueOnce(value) {
      return mock.mockImplementationOnce(function() {
        if (new.target) {
          throwConstructorError("mockResolvedValueOnce");
        }
        return Promise.resolve(value);
      });
    };
    mock.mockRejectedValue = function mockRejectedValue(value) {
      return mock.mockImplementation(function() {
        if (new.target) {
          throwConstructorError("mockRejectedValue");
        }
        return Promise.reject(value);
      });
    };
    mock.mockRejectedValueOnce = function mockRejectedValueOnce(value) {
      return mock.mockImplementationOnce(function() {
        if (new.target) {
          throwConstructorError("mockRejectedValueOnce");
        }
        return Promise.reject(value);
      });
    };
    mock.mockClear = function mockClear() {
      state.calls = [];
      state.contexts = [];
      state.instances = [];
      state.invocationCallOrder = [];
      state.results = [];
      state.settledResults = [];
      return mock;
    };
    mock.mockReset = function mockReset() {
      mock.mockClear();
      config.mockImplementation = resetToMockImplementation ? mockImplementation : void 0;
      config.mockName = resetToMockName ? mock.name || "vi.fn()" : "vi.fn()";
      config.onceMockImplementations = [];
      return mock;
    };
    mock.mockRestore = function mockRestore() {
      mock.mockReset();
      return restore?.();
    };
    mock.mockName = function mockName(name) {
      if (typeof name === "string") {
        config.mockName = name;
      }
      return mock;
    };
    mock.getMockName = function getMockName() {
      return config.mockName || "vi.fn()";
    };
    if (Symbol.dispose) {
      mock[Symbol.dispose] = () => mock.mockRestore();
    }
    if (mockImplementation) {
      mock.mockImplementation(mockImplementation);
    }
    return mock;
  }
  function fn(originalImplementation) {
    if (originalImplementation != null && isMockFunction(originalImplementation)) {
      return originalImplementation;
    }
    return createMockInstance({
      mockImplementation: originalImplementation,
      resetToMockImplementation: true
    });
  }
  function getDescriptor(obj, method) {
    const objDescriptor = Object.getOwnPropertyDescriptor(obj, method);
    if (objDescriptor) {
      return [obj, objDescriptor];
    }
    let currentProto = Object.getPrototypeOf(obj);
    while (currentProto !== null) {
      const descriptor = Object.getOwnPropertyDescriptor(currentProto, method);
      if (descriptor) {
        return [currentProto, descriptor];
      }
      currentProto = Object.getPrototypeOf(currentProto);
    }
  }
  var invocationCallCounter = 1;
  function createMock({ state, config, name: mockName, prototypeState, prototypeConfig, keepMembersImplementation, mockImplementation, prototypeMembers = [] }) {
    const original = config.mockOriginal;
    const pseudoOriginal = mockImplementation;
    const name = mockName || original?.name || "Mock";
    const namedObject = { [name]: (function(...args) {
      registerCalls(args, state, prototypeState);
      registerInvocationOrder(invocationCallCounter++, state, prototypeState);
      const result = {
        type: "incomplete",
        value: void 0
      };
      const settledResult = {
        type: "incomplete",
        value: void 0
      };
      registerResult(result, state, prototypeState);
      registerSettledResult(settledResult, state, prototypeState);
      const context = new.target ? void 0 : this;
      const [instanceIndex, instancePrototypeIndex] = registerInstance(context, state, prototypeState);
      const [contextIndex, contextPrototypeIndex] = registerContext(context, state, prototypeState);
      const implementation = config.onceMockImplementations.shift() || config.mockImplementation || prototypeConfig?.onceMockImplementations.shift() || prototypeConfig?.mockImplementation || original || function() {
      };
      let returnValue;
      let thrownValue;
      let didThrow = false;
      try {
        if (new.target) {
          returnValue = Reflect.construct(implementation, args, new.target);
          for (const prop of prototypeMembers) {
            const prototypeMock = returnValue[prop];
            if (prototypeMock !== mock.prototype[prop]) {
              continue;
            }
            const isMock = isMockFunction(prototypeMock);
            const prototypeState2 = isMock ? prototypeMock.mock : void 0;
            const prototypeConfig2 = isMock ? MOCK_CONFIGS.get(prototypeMock) : void 0;
            returnValue[prop] = createMockInstance({
              originalImplementation: keepMembersImplementation ? prototypeConfig2?.mockOriginal : void 0,
              prototypeState: prototypeState2,
              prototypeConfig: prototypeConfig2,
              keepMembersImplementation
            });
          }
        } else {
          returnValue = implementation.apply(this, args);
        }
      } catch (error) {
        thrownValue = error;
        didThrow = true;
        if (error instanceof TypeError && error.message.includes("is not a constructor")) {
          console.warn(`[vitest] The ${namedObject[name].getMockName()} mock did not use 'function' or 'class' in its implementation, see https://vitest.dev/api/vi#vi-spyon for examples.`);
        }
        throw error;
      } finally {
        if (didThrow) {
          result.type = "throw";
          result.value = thrownValue;
          settledResult.type = "rejected";
          settledResult.value = thrownValue;
        } else {
          result.type = "return";
          result.value = returnValue;
          if (new.target) {
            state.contexts[contextIndex - 1] = returnValue;
            state.instances[instanceIndex - 1] = returnValue;
            if (contextPrototypeIndex != null && prototypeState) {
              prototypeState.contexts[contextPrototypeIndex - 1] = returnValue;
            }
            if (instancePrototypeIndex != null && prototypeState) {
              prototypeState.instances[instancePrototypeIndex - 1] = returnValue;
            }
          }
          if (returnValue instanceof Promise) {
            returnValue.then((settledValue) => {
              settledResult.type = "fulfilled";
              settledResult.value = settledValue;
            }, (rejectedValue) => {
              settledResult.type = "rejected";
              settledResult.value = rejectedValue;
            });
          } else {
            settledResult.type = "fulfilled";
            settledResult.value = returnValue;
          }
        }
      }
      return returnValue;
    }) };
    const mock = namedObject[name];
    const copyPropertiesFrom = original || pseudoOriginal;
    if (copyPropertiesFrom) {
      copyOriginalStaticProperties(mock, copyPropertiesFrom);
    }
    return mock;
  }
  function registerCalls(args, state, prototypeState) {
    state.calls.push(args);
    prototypeState?.calls.push(args);
  }
  function registerInvocationOrder(order, state, prototypeState) {
    state.invocationCallOrder.push(order);
    prototypeState?.invocationCallOrder.push(order);
  }
  function registerResult(result, state, prototypeState) {
    state.results.push(result);
    prototypeState?.results.push(result);
  }
  function registerSettledResult(result, state, prototypeState) {
    state.settledResults.push(result);
    prototypeState?.settledResults.push(result);
  }
  function registerInstance(instance, state, prototypeState) {
    const instanceIndex = state.instances.push(instance);
    const instancePrototypeIndex = prototypeState?.instances.push(instance);
    return [instanceIndex, instancePrototypeIndex];
  }
  function registerContext(context, state, prototypeState) {
    const contextIndex = state.contexts.push(context);
    const contextPrototypeIndex = prototypeState?.contexts.push(context);
    return [contextIndex, contextPrototypeIndex];
  }
  function copyOriginalStaticProperties(mock, original) {
    const { properties, descriptors } = getAllProperties(original);
    for (const key of properties) {
      const descriptor = descriptors[key];
      const mockDescriptor = getDescriptor(mock, key);
      if (mockDescriptor) {
        continue;
      }
      Object.defineProperty(mock, key, descriptor);
    }
  }
  var ignoreProperties = /* @__PURE__ */ new Set([
    "length",
    "name",
    "prototype",
    Symbol.for("nodejs.util.promisify.custom")
  ]);
  function getAllProperties(original) {
    const properties = /* @__PURE__ */ new Set();
    const descriptors = {};
    while (original && original !== Object.prototype && original !== Function.prototype) {
      const ownProperties = [...Object.getOwnPropertyNames(original), ...Object.getOwnPropertySymbols(original)];
      for (const prop of ownProperties) {
        if (descriptors[prop] || ignoreProperties.has(prop)) {
          continue;
        }
        properties.add(prop);
        descriptors[prop] = Object.getOwnPropertyDescriptor(original, prop);
      }
      original = Object.getPrototypeOf(original);
    }
    return {
      properties,
      descriptors
    };
  }
  function getDefaultConfig(original) {
    return {
      mockImplementation: void 0,
      mockOriginal: original,
      mockName: "vi.fn()",
      onceMockImplementations: []
    };
  }
  function getDefaultState() {
    const state = {
      calls: [],
      contexts: [],
      instances: [],
      invocationCallOrder: [],
      settledResults: [],
      results: [],
      get lastCall() {
        return state.calls.at(-1);
      }
    };
    return state;
  }
  function throwConstructorError(shorthand) {
    throw new TypeError(`Cannot use \`${shorthand}\` when called with \`new\`. Use \`mockImplementation\` with a \`class\` keyword instead. See https://vitest.dev/api/mock#class-support for more information.`);
  }

  // ../tmp/cannbot-native-replay/node_modules/@deepseek-ai/dsh-typert-protocol/lib/index.js
  var TYPERT_OWNED_VALUE = Symbol.for("dsh.typert.owned-value");
  function isRemoteJsonValue(value) {
    return visitJsonValue(value, /* @__PURE__ */ new Set());
  }
  function isRemoteUplinkItem(value) {
    return value === void 0 || isRemoteJsonValue(value);
  }
  function visitJsonValue(value, ancestors) {
    if (value === null || typeof value === "string" || typeof value === "boolean") return true;
    if (typeof value === "number") return Number.isFinite(value) && !Object.is(value, -0);
    if (typeof value !== "object") return false;
    if (ancestors.has(value)) return false;
    ancestors.add(value);
    try {
      if (Array.isArray(value)) {
        if (Object.getPrototypeOf(value) !== Array.prototype || Reflect.ownKeys(value).length !== value.length + 1) return false;
        for (let index = 0; index < value.length; index++) if (!Object.hasOwn(value, index) || !visitJsonValue(value[index], ancestors)) return false;
        return true;
      }
      const prototype = Object.getPrototypeOf(value);
      if (prototype !== Object.prototype && prototype !== null) return false;
      for (const key of Reflect.ownKeys(value)) {
        if (typeof key !== "string") return false;
        if (Object.getOwnPropertyDescriptor(value, key)?.enumerable !== true || !visitJsonValue(Reflect.get(value, key), ancestors)) return false;
      }
      return true;
    } finally {
      ancestors.delete(value);
    }
  }

  // ../tmp/cannbot-native-replay/node_modules/@deepseek-ai/dsh-remote-mock/lib/index.js
  var MockLogStore = class {
    callEntries = [];
    streamEntries = [];
    missEntries = [];
    seq = 0;
    calls(endpoint) {
      return this.callEntries.filter((entry) => endpoint === void 0 || entry.endpoint === endpoint);
    }
    streams(endpoint) {
      return this.streamEntries.filter((entry) => endpoint === void 0 || entry.endpoint === endpoint);
    }
    requests(endpoint) {
      return [...this.calls(endpoint), ...this.streams(endpoint)].filter((entry) => endpoint !== void 0 || !entry.endpoint.startsWith("$")).sort((a, b) => a.seq - b.seq).map((entry) => entry.args[0]);
    }
    unmatched() {
      return [...this.missEntries];
    }
    /**
    * Record one call whose rule was selected.
    * @param endpoint - endpoint.
    * @param args - positional args.
    * @returns the mutable entry the dispatcher settles.
    */
    call(endpoint, args) {
      const record = {
        endpoint,
        args,
        state: "pending",
        result: void 0,
        seq: ++this.seq
      };
      this.callEntries.push(record);
      return record;
    }
    /**
    * Record one stream open.
    * @param endpoint - endpoint.
    * @param args - positional args.
    * @returns the mutable entry the stream updates.
    */
    stream(endpoint, args) {
      const record = {
        endpoint,
        args,
        state: "open",
        pushed: 0,
        seq: ++this.seq
      };
      this.streamEntries.push(record);
      return record;
    }
    /**
    * Record one request without a rule.
    * @param endpoint - endpoint.
    * @param mode - how it was requested.
    */
    miss(endpoint, mode) {
      this.missEntries.push({
        endpoint,
        mode
      });
    }
  };
  function openStream(initial = []) {
    return (_args, stream) => {
      for (const item of initial) stream.push(item);
    };
  }
  var MockStream = class {
    record;
    sourceSignal;
    uplink;
    release;
    queue = [];
    settled;
    waiting;
    drainWaiters = [];
    cancellation = new AbortController();
    signal = this.cancellation.signal;
    /** Consumer cancellation listener; attached while the stream is open, removed when it settles or cancels. */
    onAbort = () => {
      this.cancel(this.sourceSignal.reason);
    };
    /** Items pushed but not yet pulled by the consumer. */
    get queued() {
      return this.queue.length;
    }
    /**
    * @param record - log entry this stream updates.
    * @param sourceSignal - cancellation from the caller that opened the stream.
    * @param uplink - the uplink the script reads.
    * @param release - closes the uplink this stream owns; called once, when the stream settles, is cancelled, or the consumer leaves.
    */
    constructor(record, sourceSignal, uplink, release) {
      this.record = record;
      this.sourceSignal = sourceSignal;
      this.uplink = uplink;
      this.release = release;
      if (sourceSignal.aborted) this.cancel(sourceSignal.reason);
      else sourceSignal.addEventListener("abort", this.onAbort, { once: true });
    }
    push(item) {
      if (this.record.state !== "open") return;
      this.record.pushed += 1;
      if (this.waiting !== void 0) {
        const { resolve } = this.waiting;
        this.waiting = void 0;
        resolve({
          value: item,
          done: false
        });
        return;
      }
      this.queue.push(item);
    }
    end() {
      this.settle({ kind: "end" }, "ended");
    }
    fail(error) {
      this.settle({
        kind: "fail",
        error
      }, "failed");
    }
    /** The consumer left: cancel the stream and drop what it left. */
    dispose() {
      this.cancel(/* @__PURE__ */ new Error(`remote-mock: ${this.record.endpoint} stream disposed`));
    }
    /**
    * Start `script` on this stream.
    * @param script - the registered script.
    * @param args - open args.
    */
    run(script, args) {
      let outcome;
      try {
        outcome = script(args, this);
      } catch (error) {
        this.fail(toError(error));
        return;
      }
      if (outcome instanceof Promise) outcome.catch((error) => {
        this.fail(toError(error));
      });
    }
    /**
    * Resolve once the consumer has pulled every queued item and waits for the next one, or the stream is no longer
    * open and holds nothing the consumer could still pull (a consumer that returns discards what it left).
    * @returns settles when drained.
    */
    drained() {
      if (this.isDrained()) return Promise.resolve();
      return new Promise((resolve) => {
        this.drainWaiters.push(resolve);
      });
    }
    [Symbol.asyncIterator]() {
      return {
        next: () => this.next(),
        return: () => {
          this.cancel();
          return Promise.resolve({
            value: void 0,
            done: true
          });
        }
      };
    }
    next() {
      const result = this.pull();
      this.wakeDrained();
      return result;
    }
    pull() {
      if (this.queue.length > 0) return Promise.resolve({
        value: this.queue.shift(),
        done: false
      });
      if (this.settled !== void 0) return this.finish(this.settled);
      if (this.record.state === "cancelled") return Promise.resolve({
        value: void 0,
        done: true
      });
      if (this.waiting !== void 0) return Promise.reject(/* @__PURE__ */ new Error(`remote-mock: ${this.record.endpoint} stream has one consumer`));
      return new Promise((resolve, reject) => {
        this.waiting = {
          resolve,
          reject
        };
      });
    }
    finish(settled) {
      return settled.kind === "end" ? Promise.resolve({
        value: void 0,
        done: true
      }) : Promise.reject(settled.error);
    }
    settle(settled, state) {
      if (this.record.state !== "open") return;
      this.record.state = state;
      this.settled = settled;
      this.sourceSignal.removeEventListener("abort", this.onAbort);
      this.release();
      this.wakeDrained();
      const waiting = this.waiting;
      if (waiting === void 0) return;
      this.waiting = void 0;
      this.finish(settled).then(waiting.resolve, waiting.reject);
    }
    cancel(reason) {
      if (this.record.state === "open") {
        this.record.state = "cancelled";
        this.sourceSignal.removeEventListener("abort", this.onAbort);
        const waiting = this.waiting;
        this.waiting = void 0;
        this.queue.length = 0;
        this.cancellation.abort(reason);
        this.release();
        waiting?.resolve({
          value: void 0,
          done: true
        });
      }
      this.queue.length = 0;
      this.wakeDrained();
    }
    isDrained() {
      return this.queue.length === 0 && (this.waiting !== void 0 || this.record.state !== "open");
    }
    wakeDrained() {
      if (!this.isDrained()) return;
      const waiters = this.drainWaiters;
      this.drainWaiters = [];
      for (const resolve of waiters) resolve();
    }
  };
  var HandleUplink = class {
    items = [];
    done = false;
    waiter;
    /**
    * Queues one uplink item for the script, or completes the read waiting for it.
    * @param item - the item the handle's `send()` carried.
    * @throws {Error} after `end()`.
    */
    push(item) {
      if (this.done) throw new Error("remote-mock: uplink was ended");
      const waiter = this.waiter;
      this.waiter = void 0;
      if (waiter === void 0) this.items.push(item);
      else waiter({
        value: item,
        done: false
      });
    }
    /** Half-closes the uplink: pending and later reads complete as done; repeated calls are no-ops. */
    end() {
      if (this.done) return;
      this.done = true;
      this.waiter?.({
        value: void 0,
        done: true
      });
      this.waiter = void 0;
    }
    /** Ends the uplink and drops unread items; the owning stream calls it on settle or cancel, the script's iterator on `return()`. */
    close() {
      this.items.length = 0;
      this.end();
    }
    [Symbol.asyncIterator]() {
      return {
        next: () => {
          if (this.items.length > 0) return Promise.resolve({
            value: this.items.shift(),
            done: false
          });
          if (this.done) return Promise.resolve({
            value: void 0,
            done: true
          });
          return new Promise((resolve) => {
            this.waiter = resolve;
          });
        },
        return: () => {
          this.close();
          return Promise.resolve({
            value: void 0,
            done: true
          });
        }
      };
    }
  };
  var MockClientStream = class {
    stream;
    uplink;
    /**
    * @param stream - the script-side stream.
    * @param uplink - the uplink this handle feeds; absent when the carrier supplied one.
    */
    constructor(stream, uplink) {
      this.stream = stream;
      this.uplink = uplink;
    }
    send(item) {
      if (this.uplink === void 0) throw new Error(`remote-mock: ${this.stream.record.endpoint} uplink belongs to the carrier that opened the stream`);
      if (!isRemoteUplinkItem(item)) throw new Error(`remote-mock: ${this.stream.record.endpoint} uplink item is not a lossless JSON value`);
      this.uplink.push(item);
    }
    end() {
      this.uplink?.end();
    }
    dispose() {
      this.stream.dispose();
    }
    [Symbol.asyncIterator]() {
      return this.stream[Symbol.asyncIterator]();
    }
  };
  function toError(reason) {
    return reason instanceof Error ? reason : new Error(String(reason));
  }
  function createRemoteProxy(method) {
    return new Proxy(/* @__PURE__ */ Object.create(null), { get(namespaces, namespace) {
      if (typeof namespace !== "string" || namespace === "then") return void 0;
      return namespaces[namespace] ??= new Proxy(/* @__PURE__ */ Object.create(null), { get(methods, name) {
        if (typeof name !== "string" || name === "then") return void 0;
        return methods[name] = method(`${namespace}/${name}`);
      } });
    } });
  }
  var EVENTS_ENDPOINT = "$events";
  function ok(value) {
    return {
      ok: true,
      value
    };
  }
  var MissingUnaryRule = class extends Error {
  };
  var RemoteMock = class RemoteMock2 {
    /**
    * Create a mock whose `$events` stream answers the Gateway client's opening
    * with one ready frame and then stays open, so the assembled client connects.
    * @param options - host facts for the ready frame.
    * @returns the mock.
    */
    static create(options = {}) {
      const mock = new RemoteMock2();
      const host = options.host ?? { home: "/home/mock" };
      let generation = 0;
      return mock.stream(EVENTS_ENDPOINT, (_args, stream) => {
        generation += 1;
        stream.push({
          type: "ready",
          clientId: `mock-client-${String(generation)}`,
          host
        });
      });
    }
    unaryDefaults = /* @__PURE__ */ new Map();
    scripts = /* @__PURE__ */ new Map();
    live = [];
    openWaiters = [];
    logStore = new MockLogStore();
    unaryMocks = /* @__PURE__ */ new Map();
    streamMocks = /* @__PURE__ */ new Map();
    /** The carrier's uplink for the open in progress through {@link open}; a direct call has none. */
    carrierUplink;
    proxy = createRemoteProxy((endpoint) => this.modeOf(endpoint) === "stream" ? this.streamMock(endpoint) : this.unaryMock(endpoint));
    /**
    * Native mock functions for every namespace: configure answers and inspect calls without declaring method names.
    * Explicit stream registrations select stream mocks; all other methods use unary mocks.
    * Native overrides belong to this instance; `mockReset()` restores the implementation reading current defaults.
    * Generated declarations provide exact signatures; absent declarations weaken only this test-owned proxy.
    */
    remote = this.proxy;
    /** Everything observed so far. */
    log = this.logStore;
    /** Control over streams opened by registered scripts. */
    streams = {
      push: (endpoint, item, where) => this.forEachOpen(endpoint, where, (stream) => {
        stream.push(item);
      }),
      end: (endpoint, where) => this.forEachOpen(endpoint, where, (stream) => {
        stream.end();
      }),
      fail: (endpoint, error, where) => this.forEachOpen(endpoint, where, (stream) => {
        stream.fail(error);
      }),
      opened: (endpoint, count) => {
        if (this.logStore.streams(endpoint).length >= count) return Promise.resolve();
        return new Promise((resolve) => {
          this.openWaiters.push({
            endpoint,
            count,
            resolve
          });
        });
      },
      drained: (endpoint, where) => Promise.all(this.matching(endpoint, where).map((stream) => stream.drained())).then(() => void 0)
    };
    /**
    * The Connection carrier face: `call` dispatches, `open` opens; payloads carry
    * `{ args }` as the whole-client proxies (an array) or the Gateway's own
    * endpoints (one object) send them, and a call aborted by its signal rejects.
    */
    rpc = {
      call: async (_channel, endpoint, payload, signal) => {
        const pending = this.dispatch(endpoint, argsOf(endpoint, payload));
        return await (signal === void 0 ? pending : settleOrAbort(pending, signal));
      },
      open: (_channel, endpoint, payload, signal, uplink) => this.open(endpoint, argsOf(endpoint, payload), signal, uplink)
    };
    constructor() {
    }
    unary(endpoint, rule) {
      this.unaryDefaults.set(endpoint, rule);
      return this;
    }
    /**
    * Declare `endpoint` as a stream and replace its default script when supplied. A declaration without a script
    * preserves any existing script; an endpoint declared without one fails an open as a stream miss.
    * @param endpoint - `<namespace>/<method>`.
    * @param script - script (`frames` / `openStream` build the common ones).
    * @returns this.
    */
    stream(endpoint, script) {
      if (script !== void 0 || !this.scripts.has(endpoint)) this.scripts.set(endpoint, script);
      return this;
    }
    /**
    * Register endpoint defaults without changing native mock overrides.
    * @param table - unary answers and stream scripts.
    * @returns this.
    */
    load(table) {
      for (const [endpoint, rule] of Object.entries(table.unary ?? {})) this.unary(endpoint, rule);
      for (const endpoint of table.streams ?? []) this.stream(endpoint);
      for (const [endpoint, script] of Object.entries(table.stream ?? {})) this.stream(endpoint, script);
      return this;
    }
    /**
    * Whether `endpoint` is declared a stream (with or without a script) or has a unary rule — the one declaration
    * the whole-client proxies need; an endpoint neither declared nor ruled is dispatched as a unary call.
    * @param endpoint - endpoint.
    * @returns the mode, or undefined when nothing is registered.
    */
    modeOf(endpoint) {
      if (this.scripts.has(endpoint)) return "stream";
      if (this.unaryDefaults.has(endpoint)) return "unary";
    }
    /**
    * Registered endpoints and accessed proxy methods, sorted.
    * @returns endpoint names.
    */
    endpoints() {
      const names = new Set(this.scripts.keys());
      for (const endpoint of this.unaryDefaults.keys()) names.add(endpoint);
      for (const [namespace, methods] of Object.entries(this.proxy)) for (const method of Object.keys(methods)) names.add(`${namespace}/${method}`);
      return [...names].sort();
    }
    /**
    * Answer one unary call with the registered rule's value, verbatim. The call
    * is logged as soon as its rule is selected and settles with the rule: a
    * rule that throws or rejects fails the call with that error.
    * @param endpoint - endpoint.
    * @param args - positional args.
    * @returns the answer.
    * @throws {Error} when no rule is registered (logged as unmatched).
    */
    async dispatch(endpoint, args) {
      let answer;
      try {
        answer = this.unaryMock(endpoint)(...args);
      } catch (error) {
        if (error instanceof MissingUnaryRule) throw error;
        answer = Promise.reject(toError(error));
      }
      const record = this.logStore.call(endpoint, args);
      try {
        record.result = await answer;
      } catch (error) {
        record.state = "failed";
        record.result = error;
        throw error;
      }
      record.state = "answered";
      return record.result;
    }
    unaryMock(endpoint) {
      let mock = this.unaryMocks.get(endpoint);
      if (mock === void 0) {
        mock = fn((...args) => Promise.resolve(this.unaryAnswer(endpoint, args)));
        this.unaryMocks.set(endpoint, mock);
      }
      return mock;
    }
    unaryAnswer(endpoint, args) {
      if (!this.unaryDefaults.has(endpoint)) {
        this.logStore.miss(endpoint, "unary");
        throw new MissingUnaryRule(this.noRuleMessage(endpoint));
      }
      const rule = this.unaryDefaults.get(endpoint);
      return isRuleFn(rule) ? answerOf(rule, args) : rule;
    }
    /**
    * Open through the endpoint's native mock, which is called with the generated
    * signature's arguments only; its default runs the registered script as a
    * controlled stream. A native override returns its own iterable: the caller
    * owns consumption and cancellation, outside `OpenStreams`.
    * @param endpoint - endpoint.
    * @param args - positional args.
    * @param signal - consumer cancellation.
    * @param uplink - the carrier's uplink for this open, which the script reads as `StreamHandle.uplink`;
    *   absent for a direct call, whose returned handle owns the uplink.
    * @returns the controlled script stream or the native override's caller-owned iterable.
    * @throws {Error} when the default runs without a registered script (logged as unmatched).
    */
    open(endpoint, args, signal, uplink) {
      this.carrierUplink = uplink;
      try {
        return this.streamMock(endpoint)(...args, signal);
      } finally {
        this.carrierUplink = void 0;
      }
    }
    streamMock(endpoint) {
      let mock = this.streamMocks.get(endpoint);
      if (mock === void 0) {
        mock = fn((...values) => {
          const args = [...values];
          const signal = args.at(-1) instanceof AbortSignal ? args.pop() : new AbortController().signal;
          return this.openScript(endpoint, args, signal, this.carrierUplink);
        });
        this.streamMocks.set(endpoint, mock);
      }
      return mock;
    }
    openScript(endpoint, args, signal, carrierUplink) {
      const script = this.scripts.get(endpoint);
      if (script === void 0) {
        this.logStore.miss(endpoint, "stream");
        throw new Error(this.noRuleMessage(endpoint));
      }
      let uplink;
      let owned;
      if (carrierUplink === void 0) {
        owned = new HandleUplink();
        uplink = owned;
      } else uplink = carrierUplink;
      const stream = new MockStream(this.logStore.stream(endpoint, args), signal, uplink, () => {
        owned?.close();
      });
      this.live.push(stream);
      this.wakeOpened(endpoint);
      stream.run(script, args);
      return new MockClientStream(stream, owned);
    }
    /** Throw when any request found no rule, naming the endpoints and the registered ones. */
    assertNoUnmatched() {
      const unmatched = this.logStore.unmatched();
      if (unmatched.length === 0) return;
      const lines = unmatched.map((entry) => `  ${entry.endpoint} (${entry.mode})`);
      throw new Error(`remote-mock: ${String(unmatched.length)} unmatched request(s):
${lines.join("\n")}
registered: ${this.endpoints().join(", ")}`);
    }
    noRuleMessage(endpoint) {
      return `remote-mock: no rule for ${endpoint}; registered: ${this.endpoints().join(", ")}`;
    }
    /** Streams on `endpoint` still open or still holding items their consumer has not pulled; the rest are forgotten. */
    matching(endpoint, where) {
      this.live = this.live.filter((stream) => stream.record.state === "open" || stream.queued > 0);
      return this.live.filter((stream) => stream.record.endpoint === endpoint && (where === void 0 || where(stream.record.args)));
    }
    forEachOpen(endpoint, where, action) {
      const targets = this.matching(endpoint, where).filter((stream) => stream.record.state === "open");
      for (const stream of targets) action(stream);
      return targets.length;
    }
    wakeOpened(endpoint) {
      const opened = this.logStore.streams(endpoint).length;
      const ready = this.openWaiters.filter((waiter) => waiter.endpoint === endpoint && opened >= waiter.count);
      this.openWaiters = this.openWaiters.filter((waiter) => !ready.includes(waiter));
      for (const waiter of ready) waiter.resolve();
    }
  };
  function isRuleFn(rule) {
    return typeof rule === "function";
  }
  function answerOf(rule, args) {
    try {
      return rule(...args);
    } catch (error) {
      return Promise.reject(toError(error));
    }
  }
  function argsOf(endpoint, payload) {
    if (typeof payload === "object" && payload !== null && "args" in payload) {
      const { args } = payload;
      if (Array.isArray(args)) return args;
      if (typeof args === "object" && args !== null) return [args];
    }
    throw new TypeError(`remote-mock: payload of ${endpoint} must be { args: unknown[] | object }`);
  }
  function settleOrAbort(pending, signal) {
    return new Promise((resolve, reject) => {
      const abort = () => {
        reject(signal.reason instanceof Error ? signal.reason : new Error("remote-mock: call aborted", { cause: signal.reason }));
      };
      signal.addEventListener("abort", abort, { once: true });
      pending.then(resolve, reject).finally(() => {
        signal.removeEventListener("abort", abort);
      });
      if (signal.aborted) abort();
    });
  }

  // ../tmp/cannbot-native-replay/defaults.ts
  var remoteDefaultResponses = {
    unary: {
      // api-session-controller `sessions.handleConnected()` on `connection/reset`.
      "session/list": ok({ items: [] }),
      // ui-workspace startup with no entries; first-use initialization is ineligible.
      "workspace/initializeDefault": ok(void 0),
      // ui-settings `mirror.ensure()` at apply and again on `connection/reset`.
      "settings/describe": ok({ writable: true, hasDocument: false, namespaces: [] }),
      // ui-model-selection `ModelDirectoryResolver` constructor.
      "session/modelCatalog": ok({
        default: { provider: "deepseek-official", model: "deepseek-v4-flash" },
        routableProviders: [],
        groups: [],
        failures: []
      }),
      // ui-agent-preset hero chip and header label on first mount.
      "agentPresets/list": ok({ presets: [] }),
      // cordis-client-runner `ClientCordisInspectRegistry.sync` at apply and on `connection/reset`.
      "dynamicCordisRunner/syncInspectManifest": ok(null),
      // ui-cordis inventory at apply and on `connection/reset`.
      "dynamicCordisRunner/inventory": ok([]),
      // ui-settings-web-search page `readCredential()` when the settings mirror first publishes.
      "credentials/describe": ok({}),
      // ui-settings-web-search page provider options at apply and on `connection/reset`.
      "web/listProviders": ok({ search: [], fetch: [] }),
      // ui-permission-presets `PermissionCatalogDirectory` on its first read for a connection generation.
      "permissionPresets/catalog": ok({ options: [] }),
      // ui-settings-account refreshes details after a stored-grant snapshot.
      "account/getProfile": ok(null),
      "account/getBalance": ok(null),
      // ui-settings-account bonus notice read and acknowledgement at signing in.
      "account/getNotifications": ok(null),
      "account/getNotificationContent": ok(null),
      "account/reportNotificationEvent": ok(true)
    },
    // Stream endpoints the roster opens later than boot; declared so a spec that forgets the script gets a stream miss.
    streams: [
      // api-session-controller `SessionEventStream.follow` when a Session opens.
      "session/follow"
    ],
    stream: {
      "sessionStatus/follow": openStream([{ type: "baseline", items: [] }]),
      // api-session-controller client `apply`: the control stream's opening baseline, then open.
      "session/control": openStream([{ type: "baseline", value: { projections: {} } }]),
      // ui-settings-account shares the account snapshot across settings and the sidebar menu.
      "account/watch": openStream([{ type: "snapshot", state: { status: "signed-out", attempt: null, links: { usageUrl: "https://platform.deepseek.com/usage", topUpUrl: "https://platform.deepseek.com/top_up" } } }]),
      // api-workspace-controller client `apply`: the follow stream's opening baseline, then open.
      "workspace/follow": openStream([{ type: "baseline", value: { items: [], archivedSessionIds: [], pinnedSessionIds: [] } }]),
      // api-remote-access client `mountAccess`: the owner's access snapshot, then open.
      "remoteAccess/follow": openStream([{ type: "baseline", owner: true }]),
      // ui-sidebar-terminal header entry `agent-terminals`: the displayed Session's terminal roster, then open.
      "terminal/watch": openStream([[]])
    }
  };

  // ../tmp/cannbot-native-replay/fixture.json
  var fixture_default = {
    sessionList: {
      ok: true,
      value: {
        items: [
          {
            sessionId: "fx-alpha",
            updatedAt: 1789268875874,
            running: true,
            blank: false,
            cwd: "/tmp/fixture"
          },
          {
            sessionId: "fx-beta",
            updatedAt: 1789268815874,
            running: false,
            blank: false,
            parentSessionId: "fx-alpha",
            cwd: "/tmp/fixture"
          },
          {
            sessionId: "fx-gamma",
            updatedAt: 1789268755874,
            running: false,
            blank: false,
            cwd: "/tmp/fixture"
          }
        ]
      }
    },
    settingsDescribe: {
      ok: true,
      value: {
        writable: true,
        hasDocument: true,
        namespaces: [
          {
            ns: "llm-deepseek",
            schema: {},
            value: {
              apiKeyEnv: "DEEPSEEK_API_KEY"
            },
            applies: "live",
            secrets: [
              {
                path: [
                  "apiKey"
                ],
                set: false
              }
            ],
            revision: 0
          }
        ]
      }
    },
    credentialsDescribe: {
      ok: true,
      value: {
        DEEPSEEK_API_KEY: {
          configured: true,
          source: "file",
          writable: true
        }
      }
    },
    modelCatalog: {
      ok: true,
      value: {
        default: {
          provider: "deepseek-official",
          model: "deepseek-v4-flash"
        },
        routableProviders: [
          "deepseek-official",
          "openai",
          "acme-gateway"
        ],
        groups: [
          {
            id: "deepseek-official",
            name: "DeepSeek",
            models: [
              {
                id: "deepseek-v4-flash",
                name: "DeepSeek-V4-Flash",
                description: "\u5FEB\u901F\u54CD\u5E94",
                reasoning: {
                  efforts: [
                    {
                      id: "off",
                      name: "Off"
                    },
                    {
                      id: "high",
                      name: "High"
                    },
                    {
                      id: "max",
                      name: "Max"
                    }
                  ],
                  defaultEffort: "high"
                }
              },
              {
                id: "deepseek-v4-pro",
                name: "DeepSeek-V4-Pro",
                description: "\u590D\u6742\u4EFB\u52A1",
                reasoning: {
                  efforts: [
                    {
                      id: "off",
                      name: "Off"
                    },
                    {
                      id: "high",
                      name: "High"
                    },
                    {
                      id: "max",
                      name: "Max"
                    }
                  ],
                  defaultEffort: "high"
                }
              }
            ]
          },
          {
            id: "openai",
            name: "OpenAI",
            models: [
              {
                id: "gpt-5",
                name: "GPT-5",
                reasoning: {
                  efforts: [
                    {
                      id: "off",
                      name: "Off"
                    },
                    {
                      id: "medium",
                      name: "Medium"
                    },
                    {
                      id: "high",
                      name: "High"
                    },
                    {
                      id: "max",
                      name: "Max"
                    }
                  ],
                  defaultEffort: "medium"
                }
              }
            ]
          }
        ],
        failures: []
      }
    },
    agentPresets: {
      ok: true,
      value: {
        presets: [
          {
            id: "standard",
            trust: "system",
            isDefault: true
          },
          {
            id: "minimal",
            trust: "system",
            isDefault: false
          },
          {
            id: "my-agent",
            trust: "user",
            isDefault: false
          }
        ]
      }
    },
    commands: {
      ok: true,
      value: [
        {
          name: "compact",
          description: "fixture\uFF1A\u538B\u7F29\u5F53\u524D\u4F1A\u8BDD\u4E0A\u4E0B\u6587"
        },
        {
          name: "echo",
          description: "fixture\uFF1A\u56DE\u663E\u53C2\u6570",
          input: {
            hint: "text to echo"
          }
        },
        {
          definitionId: "@deepseek-ai/dsh-command-goal",
          name: "goal",
          description: "Set or view the goal for a long-running task",
          input: {
            hint: "<objective>",
            attachments: true
          }
        },
        {
          definitionId: "@deepseek-ai/dsh-permission-presets",
          name: "permission",
          description: "Switch the permission preset (sandbox mode + approval policy)",
          input: {
            hint: "<preset>"
          }
        },
        {
          definitionId: "@deepseek-ai/dsh-plan-mode",
          name: "plan",
          description: "Enter or leave plan mode",
          input: {
            hint: "[off|message]",
            attachments: true
          }
        }
      ]
    },
    workspace: {
      type: "baseline",
      value: {
        items: [
          {
            workspaceId: "fx-ws-fixture",
            path: "/tmp/fixture",
            title: "fixture",
            sessionIds: [
              "fx-alpha",
              "fx-beta",
              "fx-gamma"
            ],
            createdAt: "2026-09-13T03:02:55.884Z",
            updatedAt: "2026-09-13T03:02:55.884Z"
          },
          {
            workspaceId: "fx-ws-home",
            path: "/home/fixture/Documents/project",
            title: "project",
            sessionIds: [],
            createdAt: "2026-09-13T03:02:55.884Z",
            updatedAt: "2026-09-13T03:02:55.884Z"
          }
        ],
        archivedSessionIds: [],
        pinnedSessionIds: []
      }
    },
    control: {
      type: "baseline",
      value: {
        queues: {
          "fx-alpha": [],
          "fx-beta": [],
          "fx-gamma": []
        },
        approvals: [],
        questions: [],
        projections: {
          "fx-alpha": {
            asOfSeq: 552,
            values: {
              modelSelection: {
                lastUsed: null,
                next: null
              },
              title: "Fixture \u5386\u53F2\u4F1A\u8BDD",
              todos: [
                {
                  content: "\u68B3\u7406\u9700\u6C42",
                  status: "completed"
                },
                {
                  content: "\u5B9E\u73B0 fixture \u6837\u672C",
                  status: "in_progress"
                },
                {
                  content: "\u8DD1\u540E\u53F0\u6784\u5EFA",
                  status: "in_progress"
                },
                {
                  content: "\u6D4F\u89C8\u5668\u9A8C\u6536",
                  status: "pending"
                }
              ],
              permissions: {
                options: [
                  {
                    value: "workspace-write",
                    name: "workspace-write",
                    description: "Write inside the workspace and permitted temporary directories; wider retries require approval."
                  },
                  {
                    value: "danger-full-access",
                    name: "danger-full-access",
                    description: "Full file access without approval prompts."
                  }
                ],
                currentValue: "workspace-write"
              },
              plan: {
                active: false,
                pending: false
              },
              goal: null,
              tokenUsage: {
                uncachedInputTokens: 1914,
                outputTokens: 708,
                cacheReadTokens: 6880,
                cacheWriteTokens: 32
              },
              contextPressure: {
                pressureTokens: 104,
                contextWindow: 128e3
              },
              contextBreakdown: {
                systemTokens: 17,
                toolsTokens: 0,
                messageTokens: 4427
              },
              sessionStats: {
                turns: 75,
                steps: 87,
                llmMs: 69600,
                toolMs: 24800,
                ttftMs: 0,
                ttftSteps: 0,
                decodeMs: 0,
                decodeTokens: 0
              },
              imageLimits: {
                maxImageBytes: 5242880,
                maxImagesPerMessage: 20,
                maxMessageImageBytes: 104857600,
                maxImagePixels: 4e7,
                maxImageDimension: 2e3,
                mediaTypes: [
                  "image/png",
                  "image/jpeg",
                  "image/webp",
                  "image/gif"
                ]
              }
            }
          },
          "fx-beta": {
            asOfSeq: -1,
            values: {
              modelSelection: {
                lastUsed: null,
                next: null
              },
              todos: null,
              permissions: {
                options: [
                  {
                    value: "workspace-write",
                    name: "workspace-write",
                    description: "Write inside the workspace and permitted temporary directories; wider retries require approval."
                  },
                  {
                    value: "danger-full-access",
                    name: "danger-full-access",
                    description: "Full file access without approval prompts."
                  }
                ],
                currentValue: "workspace-write"
              },
              plan: {
                active: false,
                pending: false
              },
              goal: null,
              tokenUsage: {
                uncachedInputTokens: 0,
                outputTokens: 0,
                cacheReadTokens: 0,
                cacheWriteTokens: 0
              },
              contextPressure: {},
              contextBreakdown: {
                systemTokens: 0,
                toolsTokens: 0,
                messageTokens: 0
              },
              sessionStats: {
                turns: 0,
                steps: 0,
                llmMs: 0,
                toolMs: 0,
                ttftMs: 0,
                ttftSteps: 0,
                decodeMs: 0,
                decodeTokens: 0
              },
              imageLimits: {
                maxImageBytes: 5242880,
                maxImagesPerMessage: 20,
                maxMessageImageBytes: 104857600,
                maxImagePixels: 4e7,
                maxImageDimension: 2e3,
                mediaTypes: [
                  "image/png",
                  "image/jpeg",
                  "image/webp",
                  "image/gif"
                ]
              }
            }
          },
          "fx-gamma": {
            asOfSeq: -1,
            values: {
              modelSelection: {
                lastUsed: null,
                next: null
              },
              todos: null,
              permissions: {
                options: [
                  {
                    value: "workspace-write",
                    name: "workspace-write",
                    description: "Write inside the workspace and permitted temporary directories; wider retries require approval."
                  },
                  {
                    value: "danger-full-access",
                    name: "danger-full-access",
                    description: "Full file access without approval prompts."
                  }
                ],
                currentValue: "workspace-write"
              },
              plan: {
                active: false,
                pending: false
              },
              goal: null,
              tokenUsage: {
                uncachedInputTokens: 0,
                outputTokens: 0,
                cacheReadTokens: 0,
                cacheWriteTokens: 0
              },
              contextPressure: {},
              contextBreakdown: {
                systemTokens: 0,
                toolsTokens: 0,
                messageTokens: 0
              },
              sessionStats: {
                turns: 0,
                steps: 0,
                llmMs: 0,
                toolMs: 0,
                ttftMs: 0,
                ttftSteps: 0,
                decodeMs: 0,
                decodeTokens: 0
              },
              imageLimits: {
                maxImageBytes: 5242880,
                maxImagesPerMessage: 20,
                maxMessageImageBytes: 104857600,
                maxImagePixels: 4e7,
                maxImageDimension: 2e3,
                mediaTypes: [
                  "image/png",
                  "image/jpeg",
                  "image/webp",
                  "image/gif"
                ]
              }
            }
          }
        }
      }
    },
    remoteEvents: [
      {
        type: "ready",
        clientId: "36b204ff-b72f-4720-b58a-c86bebca8c42",
        host: {
          home: "/home/fixture"
        }
      },
      {
        type: "waterfall",
        event: "approval/request",
        eventId: "fx-interaction-approval",
        agentId: "fx-alpha",
        request: {
          toolName: "dangerous_tool",
          reason: "fixture \u5E38\u9A7B\u5BA1\u6279\uFF08\u53EF\u7B54\uFF1A\u6279\u51C6/\u62D2\u7EDD\u540E\u6D88\u5931\uFF09"
        }
      },
      {
        type: "waterfall",
        event: "user-questions/request",
        eventId: "fx-interaction-question",
        agentId: "fx-alpha",
        request: {
          questions: [
            {
              id: "harness-profile",
              header: "\u504F\u597D",
              question: "\u4F60\u73B0\u5728\u66F4\u60F3\u62DB\u54EA\u7C7B Agent/Harness \u5019\u9009\u4EBA\uFF1F",
              options: [
                {
                  label: "\u5DE5\u7A0B\u843D\u5730\u578B (Recommended)",
                  description: "\u66F4\u770B\u91CD\u80FD\u76F4\u63A5\u505A runtime\u3001tool executor\u3001sandbox\u3001trace \u548C\u7EBF\u4E0A\u95EE\u9898\u6392\u67E5\u3002"
                },
                {
                  label: "\u7814\u7A76\u6F5C\u529B\u578B",
                  description: "\u66F4\u770B\u91CD Agent \u7406\u89E3\u3001\u8BAD\u7EC3\u8BC4\u6D4B\u601D\u8DEF\u548C\u957F\u671F\u6210\u957F\u7A7A\u95F4\u3002"
                },
                {
                  label: "\u5747\u8861\u578B",
                  description: "\u540C\u65F6\u8981\u6C42\u5DE5\u7A0B\u80FD\u529B\u548C Agent \u8BA4\u77E5\uFF0C\u4F46\u53EF\u80FD\u7B5B\u9009\u95E8\u69DB\u66F4\u9AD8\u3002"
                }
              ]
            },
            {
              id: "work-mode",
              header: "\u65B9\u5F0F",
              question: "\u4F60\u5E0C\u671B\u5019\u9009\u4EBA\u4F18\u5148\u5C55\u793A\u54EA\u79CD\u5DE5\u4F5C\u65B9\u5F0F\uFF1F",
              options: [
                {
                  label: "\u5148\u505A\u5C0F\u578B\u539F\u578B (Recommended)",
                  description: "\u7528\u53EF\u8FD0\u884C\u7ED3\u679C\u5C3D\u5FEB\u9A8C\u8BC1\u5173\u952E\u5047\u8BBE\u3002"
                },
                {
                  label: "\u5148\u5199\u5B8C\u6574\u8BBE\u8BA1",
                  description: "\u5148\u6536\u655B\u8FB9\u754C\u3001\u534F\u8BAE\u548C\u98CE\u9669\uFF0C\u518D\u5F00\u59CB\u5B9E\u73B0\u3002"
                }
              ]
            },
            {
              id: "signals",
              header: "\u4FE1\u53F7",
              question: "\u54EA\u4E9B\u9762\u8BD5\u4FE1\u53F7\u6700\u91CD\u8981\uFF1F",
              detail: "\u6309\u5F53\u524D\u62DB\u8058\u76EE\u6807\u9009\u62E9\uFF1B\u8DF3\u8FC7\u5219\u89C6\u4E3A\u4E0D\u8BBE\u504F\u597D\u3002",
              multiSelect: true,
              options: [
                {
                  label: "\u7CFB\u7EDF\u8BBE\u8BA1"
                },
                {
                  label: "\u4EE3\u7801\u8D28\u91CF"
                },
                {
                  label: "Agent \u4EA7\u54C1\u5224\u65AD"
                }
              ]
            }
          ]
        }
      }
    ],
    follow: {
      type: "snapshot",
      header: {
        version: 3,
        id: "fx-alpha",
        createdAt: 1789268875874,
        cwd: "/tmp/fixture",
        isSeeded: false
      },
      cursor: 552,
      records: [
        {
          type: "event",
          event: {
            seq: 365,
            time: 1789265568675,
            type: "turn/start",
            data: {
              turn: 51
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 366,
            time: 1789265569475,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 51\uFF1Afixture \u5386\u53F2\u6D88\u606F\uFF0C\u7528\u4E8E\u7FFB\u9875\u4E0E\u6E32\u67D3\u9A8C\u6536\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "781d1628-a401-4577-9608-fad94469115f"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 367,
            time: 1789265570275,
            type: "step/start",
            data: {
              turn: 51,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 368,
            time: 1789265571075,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 51,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "text",
                    text: "\u56DE\u7B54 51\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "41db22fd-d174-446f-8d4f-dd0769071b92"
              },
              usage: {
                inputTokens: 21,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265571075,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265571075,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "text",
                      text: "\u56DE\u7B54 51\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265571075,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 21,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265571075,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 369,
            time: 1789265571875,
            type: "step/end",
            data: {
              turn: 51,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 370,
            time: 1789265572675,
            type: "turn/end",
            data: {
              turn: 51,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 371,
            time: 1789265573475,
            type: "turn/start",
            data: {
              turn: 52
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 372,
            time: 1789265574275,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 52\uFF1Afixture \u5386\u53F2\u6D88\u606F\uFF0C\u7528\u4E8E\u7FFB\u9875\u4E0E\u6E32\u67D3\u9A8C\u6536\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "ca2e9326-9086-477e-b80d-32005b85cbc6"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 373,
            time: 1789265575075,
            type: "step/start",
            data: {
              turn: 52,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 374,
            time: 1789265575875,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 52,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "reasoning",
                    text: "\u601D\u8003\u8FC7\u7A0B 52\uFF1A\u8FD9\u662F\u4E00\u6BB5\u53EF\u6298\u53E0\u7684 reasoning \u5185\u5BB9\u3002"
                  },
                  {
                    type: "text",
                    text: "\u56DE\u7B54 52\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                  },
                  {
                    type: "tool-call",
                    id: "fx-call-52",
                    name: "echo",
                    arguments: '{"text":"turn 52"}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "38c0ab81-0fc5-401d-a876-f0d1e766de03"
              },
              usage: {
                inputTokens: 22,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265575875,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "reasoning"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265575875,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "reasoning",
                      text: "\u601D\u8003\u8FC7\u7A0B 52\uFF1A\u8FD9\u662F\u4E00\u6BB5\u53EF\u6298\u53E0\u7684 reasoning \u5185\u5BB9\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265575875,
                  chunk: {
                    type: "block-start",
                    index: 1,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265575875,
                  chunk: {
                    type: "block-end",
                    index: 1,
                    block: {
                      type: "text",
                      text: "\u56DE\u7B54 52\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265575875,
                  chunk: {
                    type: "block-start",
                    index: 2,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265575875,
                  chunk: {
                    type: "block-end",
                    index: 2,
                    block: {
                      type: "tool-call",
                      id: "fx-call-52",
                      name: "echo",
                      arguments: '{"text":"turn 52"}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265575875,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 22,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265575875,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 375,
            time: 1789265576675,
            type: "tool/call",
            data: {
              turn: 52,
              step: 0,
              callId: "fx-call-52",
              name: "echo",
              arguments: '{"text":"turn 52"}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 376,
            time: 1789265577475,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 52,
              step: 0,
              message: {
                id: "e9bbfe6c-96f3-44b6-b65c-89997783be1e",
                role: "tool",
                toolCallId: "fx-call-52",
                source: {
                  kind: "tool",
                  callId: "fx-call-52"
                },
                content: [
                  {
                    type: "text",
                    text: "ECHO: TURN 52"
                  }
                ],
                isError: false
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 377,
            time: 1789265578275,
            type: "step/end",
            data: {
              turn: 52,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 378,
            time: 1789265579075,
            type: "step/start",
            data: {
              turn: 52,
              step: 1
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 379,
            time: 1789265579875,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 52,
              step: 1,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "text",
                    text: "\u5DE5\u5177\u7ED3\u679C\u5DF2\u6D88\u5316\uFF08turn 52\uFF09\u3002"
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "891ea3be-04ca-4adc-a1b5-70c311b5b0fd"
              },
              usage: {
                inputTokens: 22,
                outputTokens: 9,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265579875,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265579875,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "text",
                      text: "\u5DE5\u5177\u7ED3\u679C\u5DF2\u6D88\u5316\uFF08turn 52\uFF09\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265579875,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 22,
                      outputTokens: 9,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265579875,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 380,
            time: 1789265580675,
            type: "step/end",
            data: {
              turn: 52,
              step: 1
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 381,
            time: 1789265581475,
            type: "turn/end",
            data: {
              turn: 52,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 382,
            time: 1789265582275,
            type: "turn/start",
            data: {
              turn: 53
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 383,
            time: 1789265583075,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 53\uFF1Afixture \u5386\u53F2\u6D88\u606F\uFF0C\u7528\u4E8E\u7FFB\u9875\u4E0E\u6E32\u67D3\u9A8C\u6536\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "c26142ac-056b-47cb-bf77-6e554e565484"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 384,
            time: 1789265583875,
            type: "step/start",
            data: {
              turn: 53,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 385,
            time: 1789265584675,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 53,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "text",
                    text: "\u56DE\u7B54 53\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "cc41f0c0-2a74-4bc9-b5a2-f02f4c455569"
              },
              usage: {
                inputTokens: 23,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265584675,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265584675,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "text",
                      text: "\u56DE\u7B54 53\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265584675,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 23,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265584675,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 386,
            time: 1789265585475,
            type: "step/end",
            data: {
              turn: 53,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 387,
            time: 1789265586275,
            type: "turn/end",
            data: {
              turn: 53,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 388,
            time: 1789265587075,
            type: "turn/start",
            data: {
              turn: 54
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 389,
            time: 1789265587875,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 54\uFF1Afixture \u5386\u53F2\u6D88\u606F\uFF0C\u7528\u4E8E\u7FFB\u9875\u4E0E\u6E32\u67D3\u9A8C\u6536\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "eadaefc3-d83e-471e-ad64-8df6ae40c1eb"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 390,
            time: 1789265588675,
            type: "step/start",
            data: {
              turn: 54,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 391,
            time: 1789265589475,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 54,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "text",
                    text: "\u56DE\u7B54 54\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "b8f5e883-ce1f-42ef-8106-dfa130620801"
              },
              usage: {
                inputTokens: 24,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265589475,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265589475,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "text",
                      text: "\u56DE\u7B54 54\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265589475,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 24,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265589475,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 392,
            time: 1789265590275,
            type: "step/end",
            data: {
              turn: 54,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 393,
            time: 1789265591075,
            type: "turn/end",
            data: {
              turn: 54,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 394,
            time: 1789265591875,
            type: "turn/start",
            data: {
              turn: 55
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 395,
            time: 1789265592675,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 55\uFF1Afixture \u5386\u53F2\u6D88\u606F\uFF0C\u7528\u4E8E\u7FFB\u9875\u4E0E\u6E32\u67D3\u9A8C\u6536\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "116535cf-1160-4aff-bd8f-f89e4fc6c41f"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 396,
            time: 1789265593475,
            type: "step/start",
            data: {
              turn: 55,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 397,
            time: 1789265594275,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 55,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "reasoning",
                    text: "\u601D\u8003\u8FC7\u7A0B 55\uFF1A\u8FD9\u662F\u4E00\u6BB5\u53EF\u6298\u53E0\u7684 reasoning \u5185\u5BB9\u3002"
                  },
                  {
                    type: "text",
                    text: "\u56DE\u7B54 55\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "6a80e9b4-ca99-40ef-8de8-facbc8c27b76"
              },
              usage: {
                inputTokens: 20,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265594275,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "reasoning"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265594275,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "reasoning",
                      text: "\u601D\u8003\u8FC7\u7A0B 55\uFF1A\u8FD9\u662F\u4E00\u6BB5\u53EF\u6298\u53E0\u7684 reasoning \u5185\u5BB9\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265594275,
                  chunk: {
                    type: "block-start",
                    index: 1,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265594275,
                  chunk: {
                    type: "block-end",
                    index: 1,
                    block: {
                      type: "text",
                      text: "\u56DE\u7B54 55\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265594275,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 20,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265594275,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 398,
            time: 1789265595075,
            type: "step/end",
            data: {
              turn: 55,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 399,
            time: 1789265595875,
            type: "turn/end",
            data: {
              turn: 55,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 400,
            time: 1789265596675,
            type: "turn/start",
            data: {
              turn: 56
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 401,
            time: 1789265597475,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 56\uFF1Afixture \u5386\u53F2\u6D88\u606F\uFF0C\u7528\u4E8E\u7FFB\u9875\u4E0E\u6E32\u67D3\u9A8C\u6536\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "093791f8-cb5b-4106-853d-306ed532feec"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 402,
            time: 1789265598275,
            type: "step/start",
            data: {
              turn: 56,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 403,
            time: 1789265599075,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 56,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "text",
                    text: "\u56DE\u7B54 56\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "bc0ebb05-d212-4f30-a3eb-c4c209ff7103"
              },
              usage: {
                inputTokens: 21,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265599075,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265599075,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "text",
                      text: "\u56DE\u7B54 56\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265599075,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 21,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265599075,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 404,
            time: 1789265599875,
            type: "step/end",
            data: {
              turn: 56,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 405,
            time: 1789265600675,
            type: "turn/end",
            data: {
              turn: 56,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 406,
            time: 1789265601475,
            type: "turn/start",
            data: {
              turn: 57
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 407,
            time: 1789265602275,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 57\uFF1Afixture \u5386\u53F2\u6D88\u606F\uFF0C\u7528\u4E8E\u7FFB\u9875\u4E0E\u6E32\u67D3\u9A8C\u6536\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "4196af12-5f06-4244-a83e-281b0e2e2565"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 408,
            time: 1789265603075,
            type: "step/start",
            data: {
              turn: 57,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 409,
            time: 1789265603875,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 57,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "text",
                    text: "\u56DE\u7B54 57\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                  },
                  {
                    type: "tool-call",
                    id: "fx-call-57",
                    name: "echo",
                    arguments: '{"text":"turn 57"}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "dc114329-e3f4-43a4-bbd7-3524203a99e9"
              },
              usage: {
                inputTokens: 22,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265603875,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265603875,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "text",
                      text: "\u56DE\u7B54 57\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265603875,
                  chunk: {
                    type: "block-start",
                    index: 1,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265603875,
                  chunk: {
                    type: "block-end",
                    index: 1,
                    block: {
                      type: "tool-call",
                      id: "fx-call-57",
                      name: "echo",
                      arguments: '{"text":"turn 57"}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265603875,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 22,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265603875,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 410,
            time: 1789265604675,
            type: "tool/call",
            data: {
              turn: 57,
              step: 0,
              callId: "fx-call-57",
              name: "echo",
              arguments: '{"text":"turn 57"}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 411,
            time: 1789265605475,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 57,
              step: 0,
              message: {
                id: "652931ce-6eb0-4400-8173-9735b82fdf8e",
                role: "tool",
                toolCallId: "fx-call-57",
                source: {
                  kind: "tool",
                  callId: "fx-call-57"
                },
                content: [
                  {
                    type: "text",
                    text: "ECHO: TURN 57"
                  }
                ],
                isError: false
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 412,
            time: 1789265606275,
            type: "step/end",
            data: {
              turn: 57,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 413,
            time: 1789265607075,
            type: "step/start",
            data: {
              turn: 57,
              step: 1
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 414,
            time: 1789265607875,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 57,
              step: 1,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "text",
                    text: "\u5DE5\u5177\u7ED3\u679C\u5DF2\u6D88\u5316\uFF08turn 57\uFF09\u3002"
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "02030b82-e0d9-4e8f-a17c-bfeaa78a74d0"
              },
              usage: {
                inputTokens: 22,
                outputTokens: 9,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265607875,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265607875,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "text",
                      text: "\u5DE5\u5177\u7ED3\u679C\u5DF2\u6D88\u5316\uFF08turn 57\uFF09\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265607875,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 22,
                      outputTokens: 9,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265607875,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 415,
            time: 1789265608675,
            type: "step/end",
            data: {
              turn: 57,
              step: 1
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 416,
            time: 1789265609475,
            type: "turn/end",
            data: {
              turn: 57,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 417,
            time: 1789265610275,
            type: "turn/start",
            data: {
              turn: 58
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 418,
            time: 1789265611075,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 58\uFF1Afixture \u5386\u53F2\u6D88\u606F\uFF0C\u7528\u4E8E\u7FFB\u9875\u4E0E\u6E32\u67D3\u9A8C\u6536\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "d08478d2-30ac-49fa-b3ca-f71e8d4517ee"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 419,
            time: 1789265611875,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "[fixture] \u4E0A\u4E0B\u6587\u6CE8\u5165\uFF08turn 58\uFF09"
                }
              ],
              source: {
                kind: "plugin",
                plugin: "fixture"
              },
              role: "user",
              id: "cbb94cfa-48f7-453b-9825-e61432572399"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 420,
            time: 1789265612675,
            type: "step/start",
            data: {
              turn: 58,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 421,
            time: 1789265613475,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 58,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "reasoning",
                    text: "\u601D\u8003\u8FC7\u7A0B 58\uFF1A\u8FD9\u662F\u4E00\u6BB5\u53EF\u6298\u53E0\u7684 reasoning \u5185\u5BB9\u3002"
                  },
                  {
                    type: "text",
                    text: "\u56DE\u7B54 58\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "271e5020-8deb-418e-a4c2-d6609f31aa60"
              },
              usage: {
                inputTokens: 23,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265613475,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "reasoning"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265613475,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "reasoning",
                      text: "\u601D\u8003\u8FC7\u7A0B 58\uFF1A\u8FD9\u662F\u4E00\u6BB5\u53EF\u6298\u53E0\u7684 reasoning \u5185\u5BB9\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265613475,
                  chunk: {
                    type: "block-start",
                    index: 1,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265613475,
                  chunk: {
                    type: "block-end",
                    index: 1,
                    block: {
                      type: "text",
                      text: "\u56DE\u7B54 58\uFF1A\u8FD9\u662F fixture \u751F\u6210\u7684\u5386\u53F2\u56DE\u590D\u6B63\u6587\u3002"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265613475,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 23,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265613475,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 422,
            time: 1789265614275,
            type: "step/end",
            data: {
              turn: 58,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 423,
            time: 1789265615075,
            type: "turn/end",
            data: {
              turn: 58,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 424,
            time: 1789265615875,
            type: "turn/start",
            data: {
              turn: 59
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 425,
            time: 1789265616675,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u7528\u6237\u5B57\u9762\u91CF\uFF1A# \u4E0D\u6E32\u67D3 `code` [link](https://example.com)"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "14861e74-05a9-4e2b-b98a-c907999daa42"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 426,
            time: 1789265617475,
            type: "step/start",
            data: {
              turn: 59,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 427,
            time: 1789265618275,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 59,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "text",
                    text: "# Markdown fixture\n\nAssistant output renders **strong text**, *emphasis*, and `inline code`.\n\n- first item\n  - nested item\n\n| Area | State |\n| --- | --- |\n| history | rendered |\n| streaming | stable |\n\n[DeepSeek](https://www.deepseek.com)\n\n```ts\nconst markdown = true\n```"
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "07a55bdb-ff08-40b3-8922-0422a2f04a87"
              },
              usage: {
                inputTokens: 24,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265618275,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265618275,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "text",
                      text: "# Markdown fixture\n\nAssistant output renders **strong text**, *emphasis*, and `inline code`.\n\n- first item\n  - nested item\n\n| Area | State |\n| --- | --- |\n| history | rendered |\n| streaming | stable |\n\n[DeepSeek](https://www.deepseek.com)\n\n```ts\nconst markdown = true\n```"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265618275,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 24,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265618275,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 428,
            time: 1789265619075,
            type: "step/end",
            data: {
              turn: 59,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 429,
            time: 1789265619875,
            type: "turn/end",
            data: {
              turn: 59,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 430,
            time: 1789265620675,
            type: "turn/start",
            data: {
              turn: 60
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 431,
            time: 1789265621475,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 60\uFF1Abash \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "de206a9a-a621-435f-88f0-9613ff152eb5"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 432,
            time: 1789265622275,
            type: "step/start",
            data: {
              turn: 60,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 433,
            time: 1789265623075,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 60,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-60",
                    name: "bash",
                    arguments: '{"command":"ls -la\\necho done","description":"fixture \u7EC8\u7AEF\u6837\u672C","workdir":"/tmp/fixture"}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "4d338006-4348-4002-8a03-c730802f6f51"
              },
              usage: {
                inputTokens: 20,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 4
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265623075,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265623075,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-60",
                      name: "bash",
                      arguments: '{"command":"ls -la\\necho done","description":"fixture \u7EC8\u7AEF\u6837\u672C","workdir":"/tmp/fixture"}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265623075,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 20,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 4
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265623075,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 434,
            time: 1789265623875,
            type: "tool/call",
            data: {
              turn: 60,
              step: 0,
              callId: "fx-call-60",
              name: "bash",
              arguments: '{"command":"ls -la\\necho done","description":"fixture \u7EC8\u7AEF\u6837\u672C","workdir":"/tmp/fixture"}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 435,
            time: 1789265624675,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 60,
              step: 0,
              message: {
                id: "aa4c1898-7bec-4831-8ba1-0700f4ae897e",
                role: "tool",
                toolCallId: "fx-call-60",
                source: {
                  kind: "tool",
                  callId: "fx-call-60"
                },
                content: [
                  {
                    type: "text",
                    text: "total 2\ndrwxr-xr-x fixture\n-rw-r--r-- demo.txt"
                  }
                ],
                isError: false
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 436,
            time: 1789265625475,
            type: "step/end",
            data: {
              turn: 60,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 437,
            time: 1789265626275,
            type: "turn/end",
            data: {
              turn: 60,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 438,
            time: 1789265627075,
            type: "turn/start",
            data: {
              turn: 61
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 439,
            time: 1789265627875,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 61\uFF1Awrite \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "6fd7a2c3-2ead-41a0-b954-21883b4bc03d"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 440,
            time: 1789265628675,
            type: "step/start",
            data: {
              turn: 61,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 441,
            time: 1789265629475,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 61,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-61",
                    name: "write",
                    arguments: '{"file_path":"notes/demo.txt","content":"hello fixture\\n"}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "a3c1b7d4-200f-49b7-b550-bbc5ad98dbc9"
              },
              usage: {
                inputTokens: 21,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265629475,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265629475,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-61",
                      name: "write",
                      arguments: '{"file_path":"notes/demo.txt","content":"hello fixture\\n"}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265629475,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 21,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265629475,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 442,
            time: 1789265630275,
            type: "tool/call",
            data: {
              turn: 61,
              step: 0,
              callId: "fx-call-61",
              name: "write",
              arguments: '{"file_path":"notes/demo.txt","content":"hello fixture\\n"}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 443,
            time: 1789265631075,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 61,
              step: 0,
              message: {
                id: "4eedd943-773b-43d3-a104-e13550015670",
                role: "tool",
                toolCallId: "fx-call-61",
                source: {
                  kind: "tool",
                  callId: "fx-call-61"
                },
                content: [
                  {
                    type: "text",
                    text: "wrote notes/demo.txt"
                  }
                ],
                isError: false
              },
              meta: {
                diffs: [
                  {
                    path: "notes/demo.txt",
                    oldText: null,
                    newText: "hello fixture\n"
                  }
                ]
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 444,
            time: 1789265631875,
            type: "step/end",
            data: {
              turn: 61,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 445,
            time: 1789265632675,
            type: "turn/end",
            data: {
              turn: 61,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 446,
            time: 1789265633475,
            type: "turn/start",
            data: {
              turn: 62
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 447,
            time: 1789265634275,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 62\uFF1Aedit \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "8f4e6682-2963-4daa-a912-84ff053ac32e"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 448,
            time: 1789265635075,
            type: "step/start",
            data: {
              turn: 62,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 449,
            time: 1789265635875,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 62,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-62",
                    name: "edit",
                    arguments: '{"file_path":"notes/demo.txt","old_string":"hello","new_string":"hello fixture"}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "f1b3b777-d4ec-4b33-80ac-fa4e9d87885a"
              },
              usage: {
                inputTokens: 22,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265635875,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265635875,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-62",
                      name: "edit",
                      arguments: '{"file_path":"notes/demo.txt","old_string":"hello","new_string":"hello fixture"}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265635875,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 22,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265635875,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 450,
            time: 1789265636675,
            type: "tool/call",
            data: {
              turn: 62,
              step: 0,
              callId: "fx-call-62",
              name: "edit",
              arguments: '{"file_path":"notes/demo.txt","old_string":"hello","new_string":"hello fixture"}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 451,
            time: 1789265637475,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 62,
              step: 0,
              message: {
                id: "37d72542-2cbc-4821-8897-329da97fe462",
                role: "tool",
                toolCallId: "fx-call-62",
                source: {
                  kind: "tool",
                  callId: "fx-call-62"
                },
                content: [
                  {
                    type: "text",
                    text: "\u5DF2\u7F16\u8F91"
                  }
                ],
                isError: false
              },
              meta: {
                diffs: [
                  {
                    path: "notes/demo.txt",
                    oldText: "hello",
                    newText: "hello fixture"
                  }
                ]
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 452,
            time: 1789265638275,
            type: "step/end",
            data: {
              turn: 62,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 453,
            time: 1789265639075,
            type: "turn/end",
            data: {
              turn: 62,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 454,
            time: 1789265639875,
            type: "turn/start",
            data: {
              turn: 63
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 455,
            time: 1789265640675,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 63\uFF1Awrite \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "8e09ed22-fb26-4b3a-8ef5-1e2ac363e0f8"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 456,
            time: 1789265641475,
            type: "step/start",
            data: {
              turn: 63,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 457,
            time: 1789265642275,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 63,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-63",
                    name: "write",
                    arguments: '{"file_path":"notes/new-demo.txt","content":"hello fixture\\n"}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "65f7aa11-c436-4b13-8715-63437a194d29"
              },
              usage: {
                inputTokens: 23,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265642275,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265642275,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-63",
                      name: "write",
                      arguments: '{"file_path":"notes/new-demo.txt","content":"hello fixture\\n"}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265642275,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 23,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265642275,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 458,
            time: 1789265643075,
            type: "tool/call",
            data: {
              turn: 63,
              step: 0,
              callId: "fx-call-63",
              name: "write",
              arguments: '{"file_path":"notes/new-demo.txt","content":"hello fixture\\n"}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 459,
            time: 1789265643875,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 63,
              step: 0,
              message: {
                id: "0d0c76cf-f5b2-4f77-97cb-b0b66a67d135",
                role: "tool",
                toolCallId: "fx-call-63",
                source: {
                  kind: "tool",
                  callId: "fx-call-63"
                },
                content: [
                  {
                    type: "text",
                    text: "\u5DF2\u5199\u5165"
                  }
                ],
                isError: false
              },
              meta: {
                diffs: [
                  {
                    path: "notes/new-demo.txt",
                    oldText: null,
                    newText: "hello fixture\n"
                  }
                ]
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 460,
            time: 1789265644675,
            type: "step/end",
            data: {
              turn: 63,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 461,
            time: 1789265645475,
            type: "turn/end",
            data: {
              turn: 63,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 462,
            time: 1789265646275,
            type: "turn/start",
            data: {
              turn: 64
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 463,
            time: 1789265647075,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 64\uFF1Aedit \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "99fcaad3-6e35-4e4f-a359-f97c673c72a2"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 464,
            time: 1789265647875,
            type: "step/start",
            data: {
              turn: 64,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 465,
            time: 1789265648675,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 64,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-64",
                    name: "edit",
                    arguments: '{"file_path":"src/config.ts","old_string":"const timeout = 30","new_string":"const timeout = 60"}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "e0ae34f7-02f8-4093-a01b-e92d87fcbc3c"
              },
              usage: {
                inputTokens: 24,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265648675,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265648675,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-64",
                      name: "edit",
                      arguments: '{"file_path":"src/config.ts","old_string":"const timeout = 30","new_string":"const timeout = 60"}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265648675,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 24,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265648675,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 466,
            time: 1789265649475,
            type: "tool/call",
            data: {
              turn: 64,
              step: 0,
              callId: "fx-call-64",
              name: "edit",
              arguments: '{"file_path":"src/config.ts","old_string":"const timeout = 30","new_string":"const timeout = 60"}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 467,
            time: 1789265650275,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 64,
              step: 0,
              message: {
                id: "11a489c7-466c-45ba-a5de-228fecd455f2",
                role: "tool",
                toolCallId: "fx-call-64",
                source: {
                  kind: "tool",
                  callId: "fx-call-64"
                },
                content: [
                  {
                    type: "text",
                    text: "\u5DF2\u7F16\u8F91"
                  }
                ],
                isError: false
              },
              meta: {
                diffs: [
                  {
                    path: "src/config.ts",
                    oldText: "const timeout = 30",
                    newText: "const timeout = 60"
                  },
                  {
                    path: "src/config.ts",
                    oldText: "retries: 1",
                    newText: "retries: 3"
                  }
                ]
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 468,
            time: 1789265651075,
            type: "step/end",
            data: {
              turn: 64,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 469,
            time: 1789265651875,
            type: "turn/end",
            data: {
              turn: 64,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 470,
            time: 1789265652675,
            type: "turn/start",
            data: {
              turn: 65
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 471,
            time: 1789265653475,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 65\uFF1Arun_code \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "350becdf-2087-439b-be5e-cb19abf1dfff"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 472,
            time: 1789265654275,
            type: "step/start",
            data: {
              turn: 65,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 473,
            time: 1789265655075,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 65,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-65",
                    name: "run_code",
                    arguments: '{"code":"const listing = await tools.bash({ command: \\"ls notes\\", description: \\"List notes\\" })\\nconst demo = await tools.read({ file_path: \\"notes/demo.txt\\" })\\nawait tools.read({ file_path: \\"notes/missing.txt\\" }).catch(() => \\"tolerated\\")\\nreturn { listing, demo }","description":"Read the notes files and summarize"}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "4af251a1-bd9f-4e7a-a7e8-9d4ac6f0f8e5"
              },
              usage: {
                inputTokens: 20,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265655075,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265655075,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-65",
                      name: "run_code",
                      arguments: '{"code":"const listing = await tools.bash({ command: \\"ls notes\\", description: \\"List notes\\" })\\nconst demo = await tools.read({ file_path: \\"notes/demo.txt\\" })\\nawait tools.read({ file_path: \\"notes/missing.txt\\" }).catch(() => \\"tolerated\\")\\nreturn { listing, demo }","description":"Read the notes files and summarize"}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265655075,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 20,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265655075,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 474,
            time: 1789265655875,
            type: "tool/call",
            data: {
              turn: 65,
              step: 0,
              callId: "fx-call-65",
              name: "run_code",
              arguments: '{"code":"const listing = await tools.bash({ command: \\"ls notes\\", description: \\"List notes\\" })\\nconst demo = await tools.read({ file_path: \\"notes/demo.txt\\" })\\nawait tools.read({ file_path: \\"notes/missing.txt\\" }).catch(() => \\"tolerated\\")\\nreturn { listing, demo }","description":"Read the notes files and summarize"}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 475,
            time: 1789265656675,
            type: "tool/ptc-dispatch-start",
            data: {
              rootCallId: "fx-call-65",
              parentCallId: "fx-call-65",
              subCallId: "fx-call-65:ptc:1",
              name: "bash",
              arguments: {
                command: "ls notes",
                description: "List notes"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 476,
            time: 1789265657475,
            type: "tool/ptc-dispatch",
            data: {
              rootCallId: "fx-call-65",
              parentCallId: "fx-call-65",
              subCallId: "fx-call-65:ptc:1",
              name: "bash",
              arguments: {
                command: "ls notes",
                description: "List notes"
              },
              isError: false,
              content: [
                {
                  type: "text",
                  text: "demo.txt\nnew-demo.txt"
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 477,
            time: 1789265658275,
            type: "tool/ptc-dispatch-start",
            data: {
              rootCallId: "fx-call-65",
              parentCallId: "fx-call-65",
              subCallId: "fx-call-65:ptc:2",
              name: "read",
              arguments: {
                file_path: "notes/demo.txt"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 478,
            time: 1789265659075,
            type: "tool/ptc-dispatch",
            data: {
              rootCallId: "fx-call-65",
              parentCallId: "fx-call-65",
              subCallId: "fx-call-65:ptc:2",
              name: "read",
              arguments: {
                file_path: "notes/demo.txt"
              },
              isError: false,
              content: [
                {
                  type: "text",
                  text: "hello fixture\n"
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 479,
            time: 1789265659875,
            type: "tool/ptc-dispatch-start",
            data: {
              rootCallId: "fx-call-65",
              parentCallId: "fx-call-65",
              subCallId: "fx-call-65:ptc:3",
              name: "read",
              arguments: {
                file_path: "notes/missing.txt"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 480,
            time: 1789265660675,
            type: "tool/ptc-dispatch",
            data: {
              rootCallId: "fx-call-65",
              parentCallId: "fx-call-65",
              subCallId: "fx-call-65:ptc:3",
              name: "read",
              arguments: {
                file_path: "notes/missing.txt"
              },
              isError: true,
              content: [
                {
                  type: "text",
                  text: "Error: ENOENT: notes/missing.txt not found"
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 481,
            time: 1789265661475,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 65,
              step: 0,
              message: {
                id: "ca689e1a-ebfb-4465-b187-43c3490abb9b",
                role: "tool",
                toolCallId: "fx-call-65",
                source: {
                  kind: "tool",
                  callId: "fx-call-65"
                },
                content: [
                  {
                    type: "text",
                    text: '{"listing":"demo.txt\\nnew-demo.txt","demo":"hello fixture\\n"}'
                  }
                ],
                isError: false
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 482,
            time: 1789265662275,
            type: "step/end",
            data: {
              turn: 65,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 483,
            time: 1789265663075,
            type: "turn/end",
            data: {
              turn: 65,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 484,
            time: 1789265663875,
            type: "turn/start",
            data: {
              turn: 66
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 485,
            time: 1789265664675,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 66\uFF1Abash \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "4a5bb1d5-3698-407a-bde1-5f8acd048eab"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 486,
            time: 1789265665475,
            type: "step/start",
            data: {
              turn: 66,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 487,
            time: 1789265666275,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 66,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-66",
                    name: "bash",
                    arguments: '{"command":"pnpm run check","description":"fixture \u7EC8\u7AEF\u6837\u672C","workdir":"/tmp/fixture/deep/nested"}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "68d3d448-1cac-44fd-8a6d-5446684ac98a"
              },
              usage: {
                inputTokens: 21,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265666275,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265666275,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-66",
                      name: "bash",
                      arguments: '{"command":"pnpm run check","description":"fixture \u7EC8\u7AEF\u6837\u672C","workdir":"/tmp/fixture/deep/nested"}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265666275,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 21,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265666275,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 488,
            time: 1789265667075,
            type: "tool/call",
            data: {
              turn: 66,
              step: 0,
              callId: "fx-call-66",
              name: "bash",
              arguments: '{"command":"pnpm run check","description":"fixture \u7EC8\u7AEF\u6837\u672C","workdir":"/tmp/fixture/deep/nested"}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 489,
            time: 1789265667875,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 66,
              step: 0,
              message: {
                id: "0da2afe6-5036-4d36-b9f3-ff562585507f",
                role: "tool",
                toolCallId: "fx-call-66",
                source: {
                  kind: "tool",
                  callId: "fx-call-66"
                },
                content: [
                  {
                    type: "text",
                    text: "\x1B[1mRunning 4 checks\x1B[0m\n\x1B[32m\u2713\x1B[0m typecheck                                          1.82s\n\x1B[32m\u2713\x1B[0m lint                                               0.94s\n\x1B[32m\u2713\x1B[0m duplication                                        2.10s\n\x1B[31m\u2717\x1B[0m unit                                               8.41s\n\n\x1B[90mpackages/client/ui-primitives/tests/terminal-block.client.spec.tsx\x1B[0m\n  \x1B[31mFAIL\x1B[0m caps output at the configured line budget\n    expected 16 lines, received 24\n\nNAME                        LINES    BRANCHES    FUNCTIONS    UNCOVERED\nTerminalBlock.tsx           100%     100%        100%         -\nansi.ts                     100%     100%        100%         -\nclipboard.ts                100%     100%        100%         -\nCodeBlock.tsx               98.4%    96.2%       100%         41-43\nhighlight.ts                100%     100%        100%         -\nPill.tsx                    100%     100%        100%         -\nStateDot.tsx                100%     100%        100%         -\nmarkdown/Markdown.tsx       100%     100%        100%         -\n\n\x1B[31m1 of 4 checks failed\x1B[0m\n[exit code: 1]"
                  }
                ],
                isError: false
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 490,
            time: 1789265668675,
            type: "step/end",
            data: {
              turn: 66,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 491,
            time: 1789265669475,
            type: "turn/end",
            data: {
              turn: 66,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 492,
            time: 1789265670275,
            type: "turn/start",
            data: {
              turn: 67
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 493,
            time: 1789265671075,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 67\uFF1Agrep \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "8dab4a18-bae1-492c-a43a-8337ae80abc3"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 494,
            time: 1789265671875,
            type: "step/start",
            data: {
              turn: 67,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 495,
            time: 1789265672675,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 67,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-67",
                    name: "grep",
                    arguments: '{"pattern":"SEARCH_MAX_LINES","path":"packages/client"}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "53469dfd-6af1-4eb2-9273-53ea475b6e94"
              },
              usage: {
                inputTokens: 22,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265672675,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265672675,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-67",
                      name: "grep",
                      arguments: '{"pattern":"SEARCH_MAX_LINES","path":"packages/client"}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265672675,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 22,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265672675,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 496,
            time: 1789265673475,
            type: "tool/call",
            data: {
              turn: 67,
              step: 0,
              callId: "fx-call-67",
              name: "grep",
              arguments: '{"pattern":"SEARCH_MAX_LINES","path":"packages/client"}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 497,
            time: 1789265674275,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 67,
              step: 0,
              message: {
                id: "9a3df388-356c-4440-b0bf-b09e0dda0387",
                role: "tool",
                toolCallId: "fx-call-67",
                source: {
                  kind: "tool",
                  callId: "fx-call-67"
                },
                content: [
                  {
                    type: "text",
                    text: "Found 9 of 42 matches\n\npackages/client/ui-primitives/src/SearchBlock.tsx\nLine 16: export const DEFAULT_SEARCH_MAX_LINES = 16\nLine 138: export function SearchBlock(props: SearchBlockProps) {\nLine 141:   const [collapsed, setCollapsed] = useState<ReadonlySet<number>>(() => new Set())\npackages/client/ui-tool/src/client/tool/models/search-card-model.ts\nLine 45: export const CHAT_SEARCH_MAX_LINES = 8\nLine 130: export function searchCardModel(block: ToolCallBlock): SearchCardModel | null {\npackages/client/ui-tool/src/client/tool/toolviews/search-row.tsx\nLine 34: export function SearchRow({ toolName, block, inspect, t }: SearchRowProps) {\nLine 36:   const search = searchCardModel(block)\nLine 56:       search={search}\nLine 78:       yield ctx.slots.register({ name: 'tool.call.toolview', key: 'grep', locale: NS }, SearchRow)\n\n(Full grep result stored at: fixture://spill/grep-66. Read it to see every match.)"
                  }
                ],
                isError: false
              },
              meta: {
                shape: "matches",
                files: [
                  {
                    path: "packages/client/ui-primitives/src/SearchBlock.tsx",
                    matches: [
                      {
                        lineNumber: 16,
                        line: "export const DEFAULT_SEARCH_MAX_LINES = 16"
                      },
                      {
                        lineNumber: 138,
                        line: "export function SearchBlock(props: SearchBlockProps) {"
                      },
                      {
                        lineNumber: 141,
                        line: "  const [collapsed, setCollapsed] = useState<ReadonlySet<number>>(() => new Set())"
                      }
                    ]
                  },
                  {
                    path: "packages/client/ui-tool/src/client/tool/models/search-card-model.ts",
                    matches: [
                      {
                        lineNumber: 45,
                        line: "export const CHAT_SEARCH_MAX_LINES = 8"
                      },
                      {
                        lineNumber: 130,
                        line: "export function searchCardModel(block: ToolCallBlock): SearchCardModel | null {"
                      }
                    ]
                  },
                  {
                    path: "packages/client/ui-tool/src/client/tool/toolviews/search-row.tsx",
                    matches: [
                      {
                        lineNumber: 34,
                        line: "export function SearchRow({ toolName, block, inspect, t }: SearchRowProps) {"
                      },
                      {
                        lineNumber: 36,
                        line: "  const search = searchCardModel(block)"
                      },
                      {
                        lineNumber: 56,
                        line: "      search={search}"
                      },
                      {
                        lineNumber: 78,
                        line: "      yield ctx.slots.register({ name: 'tool.call.toolview', key: 'grep', locale: NS }, SearchRow)"
                      }
                    ]
                  }
                ],
                truncated: true,
                total: 42
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 498,
            time: 1789265675075,
            type: "step/end",
            data: {
              turn: 67,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 499,
            time: 1789265675875,
            type: "turn/end",
            data: {
              turn: 67,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 500,
            time: 1789265676675,
            type: "turn/start",
            data: {
              turn: 68
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 501,
            time: 1789265677475,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 68\uFF1Aglob \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "728f42ae-723b-485f-bf63-11b28892a89d"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 502,
            time: 1789265678275,
            type: "step/start",
            data: {
              turn: 68,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 503,
            time: 1789265679075,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 68,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-68",
                    name: "glob",
                    arguments: '{"pattern":"**/SearchBlock*","path":"packages/client"}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "b6c6950d-d67b-45eb-a718-1a4fdb241e05"
              },
              usage: {
                inputTokens: 23,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265679075,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265679075,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-68",
                      name: "glob",
                      arguments: '{"pattern":"**/SearchBlock*","path":"packages/client"}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265679075,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 23,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265679075,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 504,
            time: 1789265679875,
            type: "tool/call",
            data: {
              turn: 68,
              step: 0,
              callId: "fx-call-68",
              name: "glob",
              arguments: '{"pattern":"**/SearchBlock*","path":"packages/client"}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 505,
            time: 1789265680675,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 68,
              step: 0,
              message: {
                id: "e6d88943-d180-472b-9c1b-d59a21a50ab9",
                role: "tool",
                toolCallId: "fx-call-68",
                source: {
                  kind: "tool",
                  callId: "fx-call-68"
                },
                content: [
                  {
                    type: "text",
                    text: "packages/client/ui-primitives/src/SearchBlock.tsx\npackages/client/ui-primitives/src/SearchBlock.module.css\npackages/client/ui-tool/src/client/tool/models/search-card-model.ts\npackages/client/ui-tool/src/client/tool/toolviews/search-row.tsx\npackages/client/ui-tool/tests/search-card.client.spec.tsx\n\n(Showing 5 of 23 paths. Full sorted result stored at: fixture://spill/glob-67. Read it to see every path.)"
                  }
                ],
                isError: false
              },
              meta: {
                shape: "paths",
                paths: [
                  "packages/client/ui-primitives/src/SearchBlock.tsx",
                  "packages/client/ui-primitives/src/SearchBlock.module.css",
                  "packages/client/ui-tool/src/client/tool/models/search-card-model.ts",
                  "packages/client/ui-tool/src/client/tool/toolviews/search-row.tsx",
                  "packages/client/ui-tool/tests/search-card.client.spec.tsx"
                ],
                truncated: true,
                total: 23
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 506,
            time: 1789265681475,
            type: "step/end",
            data: {
              turn: 68,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 507,
            time: 1789265682275,
            type: "turn/end",
            data: {
              turn: 68,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 508,
            time: 1789265683075,
            type: "turn/start",
            data: {
              turn: 69
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 509,
            time: 1789265683875,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 69\uFF1Aread \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "f0564417-a09b-4e3a-8dd3-c0bd41604c23"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 510,
            time: 1789265684675,
            type: "step/start",
            data: {
              turn: 69,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 511,
            time: 1789265685475,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 69,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-69",
                    name: "read",
                    arguments: '{"file_path":"packages/client/ui-primitives/src/ReadBlock.tsx","offset":41}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "bfbff068-730d-4cf8-b647-6086e170221a"
              },
              usage: {
                inputTokens: 24,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265685475,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265685475,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-69",
                      name: "read",
                      arguments: '{"file_path":"packages/client/ui-primitives/src/ReadBlock.tsx","offset":41}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265685475,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 24,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265685475,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 512,
            time: 1789265686275,
            type: "tool/call",
            data: {
              turn: 69,
              step: 0,
              callId: "fx-call-69",
              name: "read",
              arguments: '{"file_path":"packages/client/ui-primitives/src/ReadBlock.tsx","offset":41}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 513,
            time: 1789265687075,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 69,
              step: 0,
              message: {
                id: "937c02dd-63d8-4106-9310-a9df2055f0e9",
                role: "tool",
                toolCallId: "fx-call-69",
                source: {
                  kind: "tool",
                  callId: "fx-call-69"
                },
                content: [
                  {
                    type: "text",
                    text: '<path>packages/client/ui-primitives/src/ReadBlock.tsx</path>\n<type>file</type>\n<content>\n41: export interface ReadBlockProps {\n42:   label?: string | undefined\n43:   lines: readonly ReadBlockLine[]\n44:   totalLines: number\n45:   lang?: string | undefined\n46:   maxLines?: number | undefined\n47:   className?: string | undefined\n48: }\n49: \n50: // A windowed read keeps the file line numbers in the gutter.\n51: const marker = "fixture read sample"\n\n(Showing lines 41-51 of 180. Use offset=52 to continue.)\n</content>'
                  }
                ],
                isError: false
              },
              meta: {
                path: "packages/client/ui-primitives/src/ReadBlock.tsx",
                offset: 41,
                lines: [
                  {
                    number: 41,
                    text: "export interface ReadBlockProps {"
                  },
                  {
                    number: 42,
                    text: "  label?: string | undefined"
                  },
                  {
                    number: 43,
                    text: "  lines: readonly ReadBlockLine[]"
                  },
                  {
                    number: 44,
                    text: "  totalLines: number"
                  },
                  {
                    number: 45,
                    text: "  lang?: string | undefined"
                  },
                  {
                    number: 46,
                    text: "  maxLines?: number | undefined"
                  },
                  {
                    number: 47,
                    text: "  className?: string | undefined"
                  },
                  {
                    number: 48,
                    text: "}"
                  },
                  {
                    number: 49,
                    text: ""
                  },
                  {
                    number: 50,
                    text: "// A windowed read keeps the file line numbers in the gutter."
                  },
                  {
                    number: 51,
                    text: 'const marker = "fixture read sample"'
                  }
                ],
                totalLines: 180,
                lang: "ts"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 514,
            time: 1789265687875,
            type: "step/end",
            data: {
              turn: 69,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 515,
            time: 1789265688675,
            type: "turn/end",
            data: {
              turn: 69,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 516,
            time: 1789265689475,
            type: "turn/start",
            data: {
              turn: 70
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 517,
            time: 1789265690275,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 70\uFF1Aweb_search \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "c7ba3fc7-e437-4d77-b212-e766b1ca1c47"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 518,
            time: 1789265691075,
            type: "step/start",
            data: {
              turn: 70,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 519,
            time: 1789265691875,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 70,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-70",
                    name: "web_search",
                    arguments: '{"queries":["deepseek harness architecture"]}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "70f9aaef-f006-4b53-986d-631458679ef6"
              },
              usage: {
                inputTokens: 20,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 4
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265691875,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265691875,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-70",
                      name: "web_search",
                      arguments: '{"queries":["deepseek harness architecture"]}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265691875,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 20,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 4
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265691875,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 520,
            time: 1789265692675,
            type: "tool/call",
            data: {
              turn: 70,
              step: 0,
              callId: "fx-call-70",
              name: "web_search",
              arguments: '{"queries":["deepseek harness architecture"]}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 521,
            time: 1789265693475,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 70,
              step: 0,
              message: {
                id: "c2ddb04d-74c9-4a2f-83f6-47a48fc6fbc2",
                role: "tool",
                toolCallId: "fx-call-70",
                source: {
                  kind: "tool",
                  callId: "fx-call-70"
                },
                content: [
                  {
                    type: "text",
                    text: "Search results for deepseek harness architecture."
                  }
                ],
                isError: false
              },
              meta: {
                answer: "DeepSeek Harness is a plugin-based agent harness on vendored Cordis where **every capability is a plugin**.",
                sources: [
                  {
                    url: "https://github.com/deepseek-ai/deepseek-harness",
                    title: "DeepSeek Harness \u2014 plugin-based agent harness",
                    snippet: "Everything is a plugin: session, tools, agent-loop, and LLM adapters all mount on the same Cordis context.",
                    publishedAt: "2026-07-01"
                  },
                  {
                    url: "https://www.deepseek.com/blog/harness-architecture",
                    snippet: "The capability-seam pattern splits each capability into interface, implementation, and consumer packages."
                  },
                  {
                    url: "https://docs.deepseek.com/harness/plugins",
                    title: "Writing a harness plugin",
                    publishedAt: "2026-06-15"
                  }
                ],
                truncated: true
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 522,
            time: 1789265694275,
            type: "step/end",
            data: {
              turn: 70,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 523,
            time: 1789265695075,
            type: "turn/end",
            data: {
              turn: 70,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 524,
            time: 1789265695875,
            type: "turn/start",
            data: {
              turn: 71
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 525,
            time: 1789265696675,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 71\uFF1Aweb_fetch \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "b164bd50-e038-4ada-a92e-42b483efab9a"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 526,
            time: 1789265697475,
            type: "step/start",
            data: {
              turn: 71,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 527,
            time: 1789265698275,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 71,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-71",
                    name: "web_fetch",
                    arguments: '{"url":"https://www.deepseek.com/blog/harness-architecture"}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "72a35941-d5a4-44ec-9b4d-f14303cf165b"
              },
              usage: {
                inputTokens: 21,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265698275,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265698275,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-71",
                      name: "web_fetch",
                      arguments: '{"url":"https://www.deepseek.com/blog/harness-architecture"}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265698275,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 21,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265698275,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 528,
            time: 1789265699075,
            type: "tool/call",
            data: {
              turn: 71,
              step: 0,
              callId: "fx-call-71",
              name: "web_fetch",
              arguments: '{"url":"https://www.deepseek.com/blog/harness-architecture"}'
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 529,
            time: 1789265699875,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 71,
              step: 0,
              message: {
                id: "57cf5cd3-3daf-4e2c-bb16-f8695bc2ab8c",
                role: "tool",
                toolCallId: "fx-call-71",
                source: {
                  kind: "tool",
                  callId: "fx-call-71"
                },
                content: [
                  {
                    type: "text",
                    text: "# Harness architecture\n\nEverything is a plugin."
                  }
                ],
                isError: false
              },
              meta: {
                url: "https://www.deepseek.com/blog/harness-architecture",
                statusCode: 200,
                truncated: false
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 530,
            time: 1789265700675,
            type: "step/end",
            data: {
              turn: 71,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 531,
            time: 1789265701475,
            type: "turn/end",
            data: {
              turn: 71,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 532,
            time: 1789265702275,
            type: "turn/start",
            data: {
              turn: 72
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 533,
            time: 1789265703075,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 72\uFF1A\u8BF7\u5B8C\u6574\u5217\u51FA\u5168\u90E8\u4E00\u767E\u6761\u6761\u76EE\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "35a4608a-bd98-46a2-af6a-233b28470390"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 534,
            time: 1789265703875,
            type: "step/start",
            data: {
              turn: 72,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 535,
            time: 1789265704675,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 72,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "text",
                    text: "\u6761\u76EE 1\uFF1A\u7B2C\u4E00\u6761\u3002\u6761\u76EE 2\uFF1A\u7B2C\u4E8C\u6761\u3002\u6761\u76EE 3\uFF1A\u8FD9\u4E00\u6761\u5199\u5230\u4E00\u534A\u88AB"
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "006a595a-cd1e-4137-af5c-e36dc98f354e"
              },
              usage: {
                inputTokens: 22,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265704675,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265704675,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "text",
                      text: "\u6761\u76EE 1\uFF1A\u7B2C\u4E00\u6761\u3002\u6761\u76EE 2\uFF1A\u7B2C\u4E8C\u6761\u3002\u6761\u76EE 3\uFF1A\u8FD9\u4E00\u6761\u5199\u5230\u4E00\u534A\u88AB"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265704675,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 22,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265704675,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 536,
            time: 1789265705475,
            type: "step/end",
            data: {
              turn: 72,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 537,
            time: 1789265706275,
            type: "turn/end",
            data: {
              turn: 72,
              reason: {
                kind: "max-tokens"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 538,
            time: 1789265707075,
            type: "turn/start",
            data: {
              turn: 73
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 539,
            time: 1789265707875,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "image",
                  attachment: {
                    attachmentId: "fixture:image",
                    mediaType: "image/png",
                    bytes: 247,
                    width: 160,
                    height: 90,
                    name: "fixture-image.png"
                  }
                },
                {
                  type: "text",
                  text: "\u5386\u53F2\u7528\u6237\u56FE\u7247"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "f7aa4d0e-5b76-4ccd-a566-150a227b0c27"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 540,
            time: 1789265708675,
            type: "step/start",
            data: {
              turn: 73,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 541,
            time: 1789265709475,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 73,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "text",
                    text: "\u7ED3\u6784\u5316\u6A21\u578B\u56FE\u7247\uFF1A"
                  },
                  {
                    type: "image",
                    attachment: {
                      attachmentId: "fixture:image",
                      mediaType: "image/png",
                      bytes: 247,
                      width: 160,
                      height: 90,
                      name: "fixture-image.png"
                    }
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-vision"
                },
                id: "35080466-4027-4eba-95b8-538f1447867b"
              },
              usage: {
                inputTokens: 23,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265709475,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "text"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265709475,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "text",
                      text: "\u7ED3\u6784\u5316\u6A21\u578B\u56FE\u7247\uFF1A"
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265709475,
                  chunk: {
                    type: "block-start",
                    index: 1,
                    blockType: "image"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265709475,
                  chunk: {
                    type: "block-end",
                    index: 1,
                    block: {
                      type: "image",
                      attachment: {
                        attachmentId: "fixture:image",
                        mediaType: "image/png",
                        bytes: 247,
                        width: 160,
                        height: 90,
                        name: "fixture-image.png"
                      }
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265709475,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 23,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265709475,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 542,
            time: 1789265710275,
            type: "step/end",
            data: {
              turn: 73,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 543,
            time: 1789265711075,
            type: "turn/end",
            data: {
              turn: 73,
              reason: {
                kind: "completed"
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 544,
            time: 1789265711875,
            type: "turn/start",
            data: {
              turn: 74
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 545,
            time: 1789265712675,
            type: "user/message",
            surfaceOp: "append",
            data: {
              content: [
                {
                  type: "text",
                  text: "\u95EE\u9898 74\uFF1Atodo_write \u6837\u672C\u3002"
                }
              ],
              source: {
                kind: "user"
              },
              role: "user",
              id: "df61981f-bcff-4984-9d9e-de8754da7bc8"
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 546,
            time: 1789265713475,
            type: "step/start",
            data: {
              turn: 74,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 547,
            time: 1789265714275,
            type: "assistant/message",
            surfaceOp: "append",
            data: {
              turn: 74,
              step: 0,
              message: {
                role: "assistant",
                content: [
                  {
                    type: "tool-call",
                    id: "fx-call-74",
                    name: "todo_write",
                    arguments: '{"todos":[{"content":"\u68B3\u7406\u9700\u6C42","status":"completed"},{"content":"\u5B9E\u73B0 fixture \u6837\u672C","status":"in_progress"},{"content":"\u8DD1\u540E\u53F0\u6784\u5EFA","status":"in_progress"},{"content":"\u6D4F\u89C8\u5668\u9A8C\u6536","status":"pending"}]}'
                  }
                ],
                source: {
                  kind: "model",
                  provider: "fixture",
                  model: "fx-1"
                },
                id: "c346330a-d740-45f6-9cbe-fb7b20d9f741"
              },
              usage: {
                inputTokens: 24,
                outputTokens: 8,
                cacheReadTokens: 80,
                cacheWriteTokens: 0
              },
              stream: [
                {
                  type: "chunk",
                  time: 1789265714275,
                  chunk: {
                    type: "block-start",
                    index: 0,
                    blockType: "tool-call"
                  }
                },
                {
                  type: "chunk",
                  time: 1789265714275,
                  chunk: {
                    type: "block-end",
                    index: 0,
                    block: {
                      type: "tool-call",
                      id: "fx-call-74",
                      name: "todo_write",
                      arguments: '{"todos":[{"content":"\u68B3\u7406\u9700\u6C42","status":"completed"},{"content":"\u5B9E\u73B0 fixture \u6837\u672C","status":"in_progress"},{"content":"\u8DD1\u540E\u53F0\u6784\u5EFA","status":"in_progress"},{"content":"\u6D4F\u89C8\u5668\u9A8C\u6536","status":"pending"}]}'
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265714275,
                  chunk: {
                    type: "usage",
                    usage: {
                      inputTokens: 24,
                      outputTokens: 8,
                      cacheReadTokens: 80,
                      cacheWriteTokens: 0
                    }
                  }
                },
                {
                  type: "chunk",
                  time: 1789265714275,
                  chunk: {
                    type: "finish",
                    reason: {
                      kind: "stop"
                    }
                  }
                }
              ]
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 548,
            time: 1789265715075,
            type: "tool/call",
            data: {
              turn: 74,
              step: 0,
              callId: "fx-call-74",
              name: "todo_write",
              arguments: '{"todos":[{"content":"\u68B3\u7406\u9700\u6C42","status":"completed"},{"content":"\u5B9E\u73B0 fixture \u6837\u672C","status":"in_progress"},{"content":"\u8DD1\u540E\u53F0\u6784\u5EFA","status":"in_progress"},{"content":"\u6D4F\u89C8\u5668\u9A8C\u6536","status":"pending"}]}'
            }
          }
        },
        {
          type: "event",
          event: {
            type: "todo/write",
            time: 1789265715475,
            data: {
              todos: [
                {
                  content: "\u68B3\u7406\u9700\u6C42",
                  status: "completed"
                },
                {
                  content: "\u5B9E\u73B0 fixture \u6837\u672C",
                  status: "in_progress"
                },
                {
                  content: "\u8DD1\u540E\u53F0\u6784\u5EFA",
                  status: "in_progress"
                },
                {
                  content: "\u6D4F\u89C8\u5668\u9A8C\u6536",
                  status: "pending"
                }
              ]
            },
            seq: 549
          }
        },
        {
          type: "event",
          event: {
            seq: 550,
            time: 1789265715875,
            type: "tool/result",
            surfaceOp: "append",
            data: {
              turn: 74,
              step: 0,
              message: {
                id: "499968fd-a83f-45ad-80fe-b1d73651ff13",
                role: "tool",
                toolCallId: "fx-call-74",
                source: {
                  kind: "tool",
                  callId: "fx-call-74"
                },
                content: [
                  {
                    type: "text",
                    text: "Updated todo list: 1 pending, 2 in progress, 1 completed."
                  }
                ],
                isError: false
              }
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 551,
            time: 1789265716675,
            type: "step/end",
            data: {
              turn: 74,
              step: 0
            }
          }
        },
        {
          type: "event",
          event: {
            seq: 552,
            time: 1789265717475,
            type: "turn/end",
            data: {
              turn: 74,
              reason: {
                kind: "completed"
              }
            }
          }
        }
      ],
      hasMore: true,
      projections: {
        asOfSeq: 552,
        values: {
          modelSelection: {
            lastUsed: null,
            next: null
          },
          title: "Fixture \u5386\u53F2\u4F1A\u8BDD",
          todos: [
            {
              content: "\u68B3\u7406\u9700\u6C42",
              status: "completed"
            },
            {
              content: "\u5B9E\u73B0 fixture \u6837\u672C",
              status: "in_progress"
            },
            {
              content: "\u8DD1\u540E\u53F0\u6784\u5EFA",
              status: "in_progress"
            },
            {
              content: "\u6D4F\u89C8\u5668\u9A8C\u6536",
              status: "pending"
            }
          ],
          permissions: {
            options: [
              {
                value: "workspace-write",
                name: "workspace-write",
                description: "Write inside the workspace and permitted temporary directories; wider retries require approval."
              },
              {
                value: "danger-full-access",
                name: "danger-full-access",
                description: "Full file access without approval prompts."
              }
            ],
            currentValue: "workspace-write"
          },
          plan: {
            active: false,
            pending: false
          },
          goal: null,
          tokenUsage: {
            uncachedInputTokens: 1914,
            outputTokens: 708,
            cacheReadTokens: 6880,
            cacheWriteTokens: 32
          },
          contextPressure: {
            pressureTokens: 104,
            contextWindow: 128e3
          },
          contextBreakdown: {
            systemTokens: 17,
            toolsTokens: 0,
            messageTokens: 4427
          },
          sessionStats: {
            turns: 75,
            steps: 87,
            llmMs: 69600,
            toolMs: 24800,
            ttftMs: 0,
            ttftSteps: 0,
            decodeMs: 0,
            decodeTokens: 0
          },
          imageLimits: {
            maxImageBytes: 5242880,
            maxImagesPerMessage: 20,
            maxMessageImageBytes: 104857600,
            maxImagePixels: 4e7,
            maxImageDimension: 2e3,
            mediaTypes: [
              "image/png",
              "image/jpeg",
              "image/webp",
              "image/gif"
            ]
          }
        }
      },
      assistantStream: {
        revision: 0
      }
    },
    attachment: {
      ok: true,
      value: {
        attachment: {
          attachmentId: "fixture:image",
          mediaType: "image/png",
          bytes: 247,
          width: 160,
          height: 90,
          name: "fixture-image.png"
        },
        data: "iVBORw0KGgoAAAANSUhEUgAAAKAAAABaCAYAAAA/xl1SAAAAvklEQVR42u3SMQ0AAAjAMIyhELM4AAe8PD1qYFlk9cCXEAEDYkAwIAYEA2JAMCAGBANiQDAgBgQDYkAwIAYEA2JAMCAGBANiQDAgBgQDYkAwIAYEA2JAMCAGxIBCYEAMCAbEgGBADAgGxIBgQAwIBsSAYEAMCAbEgGBADAgGxIBgQAwIBsSAYEAMCAbEgGBADAgGxIAYEAyIAcGAGBAMiAHBgBgQDIgBwYAYEAyIAcGAGBAMiAHBgBgQDIgB4bYWLb6pnOb1xAAAAABJRU5ErkJggg=="
      }
    }
  };

  // ../tmp/cannbot-native-replay/native-session-records.json
  var native_session_records_default = [
    {
      type: "event",
      event: {
        type: "turn/start",
        seq: 4,
        time: -167,
        data: {
          turn: 1
        }
      }
    },
    {
      type: "event",
      event: {
        type: "step/start",
        seq: 6,
        time: -4,
        data: {
          turn: 1,
          step: 1
        }
      }
    },
    {
      type: "event",
      event: {
        type: "user/message",
        seq: 8,
        time: 0,
        data: {
          role: "user",
          id: "5e09e73a-2393-43bd-8f29-6a2994b75b57",
          source: {
            kind: "user",
            rpcId: "e6560768-8d9d-4426-afa7-7c469cadf88a",
            clientTimeZone: "Asia/Shanghai"
          },
          content: [
            {
              type: "text",
              text: "FP32 vector addition"
            }
          ]
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "assistant/message",
        seq: 22,
        time: 9189,
        data: {
          turn: 1,
          step: 1,
          message: {
            role: "assistant",
            id: "a17af8f4-5a95-43ce-b217-d272912753da",
            source: {
              kind: "model",
              provider: "deepseek-official",
              model: "deepseek-flash",
              replayState: {
                response: {
                  kind: "deepseek-messages",
                  version: 1,
                  model: "deepseek-flash"
                },
                blocks: [
                  {
                    type: "reasoning",
                    signature: "a2620e67-d29c-4644-ad0a-3acf8c8bad20"
                  },
                  {
                    type: "tool-call"
                  },
                  {
                    type: "tool-call"
                  }
                ]
              }
            },
            content: [
              {
                type: "reasoning",
                text: 'The user asks: "\u5F00\u53D1\u4E00\u4E2Aadd\u7B97\u5B50" (Develop an add operator). The workspace AGENTS.md gives a specific restricted demo runner: for FP32 vector-add, call `cannbot-npu-check add`. That\'s the designated path \u2014 this is a demo workspace, not a full CANN dev enviro'
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "tool/call",
        seq: 23,
        time: 9193,
        data: {
          turn: 1,
          step: 1,
          callId: "call_00_qfLw17ivuyRhtTf8QjFh2891",
          name: "skill",
          arguments: '{"name": "ops-direct-invoke"}'
        }
      }
    },
    {
      type: "event",
      event: {
        type: "tool/result",
        seq: 24,
        time: 9321,
        data: {
          turn: 1,
          step: 1,
          message: {
            role: "tool",
            id: "4fa3b201-50f7-48f9-9d52-f86f77adae19",
            source: {
              kind: "tool",
              callId: "call_00_qfLw17ivuyRhtTf8QjFh2891"
            },
            toolCallId: "call_00_qfLw17ivuyRhtTf8QjFh2891",
            isError: false,
            content: [
              {
                type: "text",
                text: "Load operator workflow"
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "tool/call",
        seq: 25,
        time: 9323,
        data: {
          turn: 1,
          step: 1,
          callId: "call_01_OHhdlAqEDoGG1EX9pTC31444",
          name: "bash",
          arguments: '{"description": "List workspace contents and runner", "command": "[command omitted from public replay]"}'
        }
      }
    },
    {
      type: "event",
      event: {
        type: "tool/result",
        seq: 29,
        time: 9433,
        data: {
          turn: 1,
          step: 1,
          message: {
            role: "tool",
            id: "09875944-f7a6-4d22-8de8-0a7e8813b392",
            source: {
              kind: "tool",
              callId: "call_01_OHhdlAqEDoGG1EX9pTC31444"
            },
            toolCallId: "call_01_OHhdlAqEDoGG1EX9pTC31444",
            isError: false,
            content: [
              {
                type: "text",
                text: "List workspace contents and runner"
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "step/end",
        seq: 30,
        time: 9434,
        data: {
          turn: 1,
          step: 1
        }
      }
    },
    {
      type: "event",
      event: {
        type: "step/start",
        seq: 31,
        time: 9479,
        data: {
          turn: 1,
          step: 2
        }
      }
    },
    {
      type: "event",
      event: {
        type: "assistant/message",
        seq: 34,
        time: 12360,
        data: {
          turn: 1,
          step: 2,
          message: {
            role: "assistant",
            id: "2fb9d4b8-df8d-4d80-9787-35502d86144c",
            source: {
              kind: "model",
              provider: "deepseek-official",
              model: "deepseek-flash",
              replayState: {
                response: {
                  kind: "deepseek-messages",
                  version: 1,
                  model: "deepseek-flash"
                },
                blocks: [
                  {
                    type: "reasoning",
                    signature: "b6391228-e3d2-4c2c-a13d-c1c9cdb3c7f3"
                  },
                  {
                    type: "tool-call"
                  }
                ]
              }
            },
            content: [
              {
                type: "reasoning",
                text: "Now I have the ops-direct-invoke PM skill. But AGENTS.md says this is a restricted demo: for add, call the runner immediately with exactly one command. That is an explicit, more specific workspace instruction. The PM skill says to align requirements with questionnaires, run workf"
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "tool/call",
        seq: 35,
        time: 12363,
        data: {
          turn: 1,
          step: 2,
          callId: "call_00_HEjxBW5FmbD076KgGXKH3571",
          name: "bash",
          arguments: '{"description": "Inspect runner and workspace metadata", "command": "[command omitted from public replay]"}'
        }
      }
    },
    {
      type: "event",
      event: {
        type: "tool/result",
        seq: 39,
        time: 12438,
        data: {
          turn: 1,
          step: 2,
          message: {
            role: "tool",
            id: "9582d187-0194-4db9-84a3-c6eef386aad3",
            source: {
              kind: "tool",
              callId: "call_00_HEjxBW5FmbD076KgGXKH3571"
            },
            toolCallId: "call_00_HEjxBW5FmbD076KgGXKH3571",
            isError: false,
            content: [
              {
                type: "text",
                text: "Inspect runner and workspace metadata"
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "step/end",
        seq: 40,
        time: 12440,
        data: {
          turn: 1,
          step: 2
        }
      }
    },
    {
      type: "event",
      event: {
        type: "step/start",
        seq: 41,
        time: 12499,
        data: {
          turn: 1,
          step: 3
        }
      }
    },
    {
      type: "event",
      event: {
        type: "assistant/message",
        seq: 44,
        time: 15874,
        data: {
          turn: 1,
          step: 3,
          message: {
            role: "assistant",
            id: "5a210b1c-9aa5-436e-be46-baffaaa7b1a0",
            source: {
              kind: "model",
              provider: "deepseek-official",
              model: "deepseek-flash",
              replayState: {
                response: {
                  kind: "deepseek-messages",
                  version: 1,
                  model: "deepseek-flash"
                },
                blocks: [
                  {
                    type: "reasoning",
                    signature: "6813d019-03ea-4364-8e73-3706ea3250db"
                  },
                  {
                    type: "tool-call"
                  },
                  {
                    type: "tool-call"
                  }
                ]
              }
            },
            content: [
              {
                type: "reasoning",
                text: "Now, the plan. The demo environment: AGENTS.md says for add, call the runner with exactly one command. Requirement is clear (add, FP32). No questionnaire needed \u2014 the demo is pre-aligned. I'll set up a todo plan, run the runner, then write a short record and report.\n\nLet me creat"
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "tool/call",
        seq: 45,
        time: 15879,
        data: {
          turn: 1,
          step: 3,
          callId: "call_00_0qr1wFp9BXTIZxfQYGCB8534",
          name: "todo_write",
          arguments: '{"todos": [{"content": "\u9700\u6C42\u4E0E\u73AF\u5883\u5BF9\u9F50\uFF1A\u786E\u8BA4\u7B97\u5B50\u4E3A add\uFF08FP32 \u9010\u5143\u7D20\uFF09\u3001\u76EE\u6807\u82AF\u7247 Ascend 950PR\u3001\u4EC5\u53EF\u7528\u53D7\u9650 NPU runner", "status": "in_progress"}, {"content": "\u8FD0\u884C\u53D7\u9650 NPU runner \u5728\u771F\u673A\u7F16\u8BD1\u5E76\u6267\u884C add \u6838\u51FD\u6570", "status": "pending"}, {"content": "\u6838\u5BF9 runner \u8F93\u51FA\uFF1Adevice / \u5143\u7D20\u6570 / \u6700\u5927\u8BEF\u5DEE / \u662F\u5426\u901A\u8FC7", "status": "pending"}, {"content": "\u843D\u76D8\u9A8C\u8BC1\u8BB0\u5F55\uFF08\u65E5\u5FD7 + STATE \u6458\u8981\uFF09\u5E76\u6C47\u62A5\u4EA4\u4ED8", "status": "pending"}]}'
        }
      }
    },
    {
      type: "event",
      event: {
        type: "tool/result",
        seq: 47,
        time: 15903,
        data: {
          turn: 1,
          step: 3,
          message: {
            role: "tool",
            id: "beb18d47-1c1b-4a05-9330-ce5f7bf579ae",
            source: {
              kind: "tool",
              callId: "call_00_0qr1wFp9BXTIZxfQYGCB8534"
            },
            toolCallId: "call_00_0qr1wFp9BXTIZxfQYGCB8534",
            isError: false,
            content: [
              {
                type: "text",
                text: "Update tasks"
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "tool/call",
        seq: 48,
        time: 15904,
        data: {
          turn: 1,
          step: 3,
          callId: "call_01_hKLAA7iGm5m4w0sTybkf3645",
          name: "bash",
          arguments: '{"description": "Run add kernel on remote NPU", "command": "cannbot-npu-check add"}'
        }
      }
    },
    {
      type: "event",
      event: {
        type: "tool/result",
        seq: 51,
        time: 28745,
        data: {
          turn: 1,
          step: 3,
          message: {
            role: "tool",
            id: "a2b9fec1-ad0e-41ff-b565-fed237b40966",
            source: {
              kind: "tool",
              callId: "call_01_hKLAA7iGm5m4w0sTybkf3645"
            },
            toolCallId: "call_01_hKLAA7iGm5m4w0sTybkf3645",
            isError: false,
            content: [
              {
                type: "text",
                text: "operation=add host=[NPU host] device=Ascend950PR\n        AscendC::Add(zLocal, xLocal, yLocal, count);\n        AscendC::Reg::Add(dstReg, srcReg0, srcReg1, mask);\n[ 50%] Building ASC object CMakeFiles/add_custom.dir/op_host/add_custom.asc.o\n[100%] Linking ASC executable add_custom\n[100%] Built target add_custom\nGenerated test data: 32768 elements, dtype=<class 'numpy.float32'>\n  input/input_x.bin: (32768,), float32\n  input/input_y.bin: (32768,), float32\n  output/golden.bin: (32768,), float32\nVerification PASSED! Shape: (32768,)\nMax diff: 0.0\n[exit: 0]"
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "step/end",
        seq: 52,
        time: 28746,
        data: {
          turn: 1,
          step: 3
        }
      }
    },
    {
      type: "event",
      event: {
        type: "step/start",
        seq: 53,
        time: 28830,
        data: {
          turn: 1,
          step: 4
        }
      }
    },
    {
      type: "event",
      event: {
        type: "assistant/message",
        seq: 56,
        time: 37036,
        data: {
          turn: 1,
          step: 4,
          message: {
            role: "assistant",
            id: "f6409810-2b7a-4a9c-8eca-047edbb351fa",
            source: {
              kind: "model",
              provider: "deepseek-official",
              model: "deepseek-flash",
              replayState: {
                response: {
                  kind: "deepseek-messages",
                  version: 1,
                  model: "deepseek-flash"
                },
                blocks: [
                  {
                    type: "reasoning",
                    signature: "eb55f5f5-8945-43f9-a330-cd2b278c9ed0"
                  },
                  {
                    type: "tool-call"
                  },
                  {
                    type: "tool-call"
                  }
                ]
              }
            },
            content: [
              {
                type: "reasoning",
                text: "The runner succeeded. Output: operation=add host=[NPU host] device=Ascend950PR, built add_custom, generated 32768 elements float32, Verification PASSED, Max diff 0.0.\n\nNow record the artifacts. Write a log file with actual output and a STATE.md summary. Let me create .cannbot/a"
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "tool/call",
        seq: 57,
        time: 37039,
        data: {
          turn: 1,
          step: 4,
          callId: "call_00_Fz9DWGTt2PyZlmuh4CAY6227",
          name: "write",
          arguments: '{"file_path": "1-NPU\u9A8C\u8BC1\u65E5\u5FD7.log"}'
        }
      }
    },
    {
      type: "event",
      event: {
        type: "tool/result",
        seq: 58,
        time: 37112,
        data: {
          turn: 1,
          step: 4,
          message: {
            role: "tool",
            id: "cd023da8-3094-49e3-a16a-51dbb711e249",
            source: {
              kind: "tool",
              callId: "call_00_Fz9DWGTt2PyZlmuh4CAY6227"
            },
            toolCallId: "call_00_Fz9DWGTt2PyZlmuh4CAY6227",
            isError: false,
            content: [
              {
                type: "text",
                text: "Save NPU validation log"
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "tool/call",
        seq: 59,
        time: 37114,
        data: {
          turn: 1,
          step: 4,
          callId: "call_01_i5RxOcm0uhuwPYopyR7W3817",
          name: "write",
          arguments: '{"file_path": "STATE.md"}'
        }
      }
    },
    {
      type: "event",
      event: {
        type: "tool/result",
        seq: 60,
        time: 37211,
        data: {
          turn: 1,
          step: 4,
          message: {
            role: "tool",
            id: "b2d8ec70-d800-40c6-91bc-e1d511cc2d8a",
            source: {
              kind: "tool",
              callId: "call_01_i5RxOcm0uhuwPYopyR7W3817"
            },
            toolCallId: "call_01_i5RxOcm0uhuwPYopyR7W3817",
            isError: false,
            content: [
              {
                type: "text",
                text: "Save workflow status"
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "step/end",
        seq: 61,
        time: 37213,
        data: {
          turn: 1,
          step: 4
        }
      }
    },
    {
      type: "event",
      event: {
        type: "step/start",
        seq: 62,
        time: 37268,
        data: {
          turn: 1,
          step: 5
        }
      }
    },
    {
      type: "event",
      event: {
        type: "assistant/message",
        seq: 65,
        time: 39809,
        data: {
          turn: 1,
          step: 5,
          message: {
            role: "assistant",
            id: "0b89c475-01b2-4f97-a8b1-2975bb0bf47f",
            source: {
              kind: "model",
              provider: "deepseek-official",
              model: "deepseek-flash",
              replayState: {
                response: {
                  kind: "deepseek-messages",
                  version: 1,
                  model: "deepseek-flash"
                },
                blocks: [
                  {
                    type: "reasoning",
                    signature: "85bafffb-aa01-47fd-a9ea-6685bc893f14"
                  },
                  {
                    type: "tool-call"
                  }
                ]
              }
            },
            content: [
              {
                type: "reasoning",
                text: "Update todos to completed, then report.\n\nShould I use present? The deliverables are log files; a card might be useful but instructions say don't call present just to list edited source files. It's a log/state doc \u2014 inline links suffice. I'll link them.\n\nLet me mark todos."
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "tool/call",
        seq: 66,
        time: 39815,
        data: {
          turn: 1,
          step: 5,
          callId: "call_00_MTW8yicbGlEmlL6b7h1S4277",
          name: "todo_write",
          arguments: '{"todos": [{"content": "\u9700\u6C42\u4E0E\u73AF\u5883\u5BF9\u9F50\uFF1A\u786E\u8BA4\u7B97\u5B50\u4E3A add\uFF08FP32 \u9010\u5143\u7D20\uFF09\u3001\u76EE\u6807\u82AF\u7247 Ascend 950PR\u3001\u4EC5\u53EF\u7528\u53D7\u9650 NPU runner", "status": "completed"}, {"content": "\u8FD0\u884C\u53D7\u9650 NPU runner \u5728\u771F\u673A\u7F16\u8BD1\u5E76\u6267\u884C add \u6838\u51FD\u6570", "status": "completed"}, {"content": "\u6838\u5BF9 runner \u8F93\u51FA\uFF1Adevice / \u5143\u7D20\u6570 / \u6700\u5927\u8BEF\u5DEE / \u662F\u5426\u901A\u8FC7", "status": "completed"}, {"content": "\u843D\u76D8\u9A8C\u8BC1\u8BB0\u5F55\uFF08\u65E5\u5FD7 + STATE \u6458\u8981\uFF09\u5E76\u6C47\u62A5\u4EA4\u4ED8", "status": "completed"}]}'
        }
      }
    },
    {
      type: "event",
      event: {
        type: "tool/result",
        seq: 68,
        time: 39918,
        data: {
          turn: 1,
          step: 5,
          message: {
            role: "tool",
            id: "eb73a475-fbd1-4cdb-80fe-b522a70af10f",
            source: {
              kind: "tool",
              callId: "call_00_MTW8yicbGlEmlL6b7h1S4277"
            },
            toolCallId: "call_00_MTW8yicbGlEmlL6b7h1S4277",
            isError: false,
            content: [
              {
                type: "text",
                text: "Complete tasks"
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "step/end",
        seq: 69,
        time: 39920,
        data: {
          turn: 1,
          step: 5
        }
      }
    },
    {
      type: "event",
      event: {
        type: "step/start",
        seq: 70,
        time: 39994,
        data: {
          turn: 1,
          step: 6
        }
      }
    },
    {
      type: "event",
      event: {
        type: "assistant/message",
        seq: 73,
        time: 44886,
        data: {
          turn: 1,
          step: 6,
          message: {
            role: "assistant",
            id: "360b8b04-34d4-47e0-8407-282b446fef9b",
            source: {
              kind: "model",
              provider: "deepseek-official",
              model: "deepseek-flash",
              replayState: {
                response: {
                  kind: "deepseek-messages",
                  version: 1,
                  model: "deepseek-flash"
                },
                blocks: [
                  {
                    type: "reasoning",
                    signature: "e7ea64d0-f4fb-453f-af8d-3a56e20cf5e5"
                  },
                  {
                    type: "text"
                  }
                ]
              }
            },
            content: [
              {
                type: "reasoning",
                text: "Report with actual output. Include the numbers: device Ascend950PR, 32768 elements float32, max diff 0.0, PASSED, exit 0.\n\nBe honest about how it was produced (restricted demo runner, kernel materialized server-side; local workspace has no kernel source or pytest suite)."
              },
              {
                type: "text",
                text: "`add` \u7B97\u5B50\u5DF2\u5728\u771F\u5B9E Ascend 950PR \u4E0A\u8DD1\u901A\u5E76\u4E0E NumPy \u5BF9\u62CD\u901A\u8FC7\u3002\n\n## \u9A8C\u8BC1\u7ED3\u679C\uFF08\u771F\u5B9E\u8F93\u51FA\uFF09\n\n| \u9879 | \u503C |\n|---|---|\n| device | `Ascend950PR`\uFF08host \u5BB9\u5668 `[NPU host]`\uFF09 |\n| \u7B97\u5B50 | `add`\uFF0C`out = x + y` |\n| \u6570\u636E\u89C4\u6A21 | 32768 \u5143\u7D20\uFF0C`float32` |\n| golden | NumPy \u53C2\u8003\u5B9E\u73B0 |\n| \u6BD4\u5BF9\u7ED3\u8BBA | `Verification PASSED! Shape: (32768,)` |\n| \u6700\u5927\u7EDD\u5BF9\u8BEF\u5DEE | `0.0` |\n| \u6784\u5EFA | `Built target add_custom`\uFF08CANN\uFF0C\u9000\u51FA\u7801 0\uFF09 |\n\nrunner \u4FA7\u4F7F\u7528\u7684\u8BA1\u7B97\u8DEF\u5F84\u5370\u8BC1\u5728\u65E5\u5FD7\u91CC\uFF1A\u65E2\u6709\u7ECF\u5178\u5411\u91CF\u5F62\u6001 `AscendC::Add(zLocal, xLocal, yLocal, count);`\uFF0C\u4E5F\u6709 Ascend950 \u7684 Reg \u5F62\u6001 `AscendC::Reg::Add(dstReg, srcReg0, srcReg1, mask);`\u3002\n\n## \u6267\u884C\u65B9\u5F0F\u4E0E\u8FB9\u754C\n\n\u672C\u5DE5\u4F5C\u533A\uFF08web host\uFF09\u6CA1\u6709 CANN / torch_npu\uFF0C\u6309\u5DE5\u4F5C\u533A\u7EA6\u5B9A\u901A\u8FC7\u53D7\u9650 demo runner \u6267\u884C\uFF1A`cannbot-npu-check add`\u3002\u8BE5 runner \u5728\u8FDC\u7AEF NPU \u4E3B\u673A\u4E0A\u7269\u5316 demo kernel\u3001\u7528 CANN \u6784\u5EFA\u3001\u8DD1 32768 \u5143\u7D20\u7528\u4F8B\u5E76\u4E0E NumPy \u5BF9\u62CD\u3002\n\n\u56E0\u6B64\u9700\u8981\u8BF4\u660E\u6E05\u695A\uFF1A**kernel \u6E90\u7801\u7531 runner \u4FA7\u63D0\u4F9B\uFF0C\u672C\u5DE5\u4F5C\u533A\u6CA1\u6709\u4FDD\u7559 `.asc` / `CMakeLists.txt` / pytest \u5957\u4EF6\uFF0C\u6211\u4E5F\u6CA1\u6709\u5BF9\u672C\u5730\u4EE3\u7801\u505A\u8FC7\u7F16\u8F91**\u2014\u2014\u672C\u6B21\u4EA4\u4ED8\u662F\u8FD9\u6761 `add` \u8DEF\u5F84\u7684\u7AEF\u5230\u7AEF\u771F\u673A\u9A8C\u8BC1\uFF0C\u800C\u975E\u4E00\u4EFD\u672C\u5730\u53EF\u7EF4\u62A4\u7684\u7B97\u5B50\u5DE5\u7A0B\u3002\u82E5\u4F60\u9700\u8981\u672C\u5730\u5DE5\u7A0B\u5F62\u6001\uFF08`add.asc` + CMake + pytest \u53C2\u6570\u5316\u5957\u4EF6\uFF0C\u53EF\u81EA\u5B9A\u4E49 shape/dtype\uFF09\uFF0C\u6211\u53EF\u4EE5\u6309 `ops-direct-invoke-flash` \u7684\u7ED3\u6784\u5728\u8FD9\u91CC\u8D77\u8349\uFF0C\u4F46\u90A3\u6837\u7684\u4EE3\u7801\u65E0\u6CD5\u7528\u8FD9\u4E2A runner \u9A8C\u8BC1\uFF1B\u9A8C\u8BC1\u9700\u8981\u5728\u6709 CANN \u7684\u673A\u5668\u4E0A\u505A\u3002\n\n\n\n## \u4EA7\u7269\n\n- [NPU \u9A8C\u8BC1\u539F\u59CB\u65E5\u5FD7](" + new URL("../replay/npu-validation.log", document.baseURI).href + ")\n- [STATE.md](" + new URL("../replay/STATE.md", document.baseURI).href + ")\n\n## \u987A\u5E26\u53EF\u505A\n\nrunner \u8FD8\u652F\u6301 `sub`\uFF08FP32 \u9010\u5143\u7D20\u51CF\u6CD5\uFF09\u3002\u9700\u8981\u51CF\u6CD5 demo \u6216\u60F3\u8981\u672C\u5730\u5DE5\u7A0B\u5F62\u6001\u7684 `add`\uFF0C\u544A\u8BC9\u6211\u5373\u53EF\u3002"
              }
            ]
          }
        },
        surfaceOp: "append"
      }
    },
    {
      type: "event",
      event: {
        type: "step/end",
        seq: 74,
        time: 44888,
        data: {
          turn: 1,
          step: 6
        }
      }
    },
    {
      type: "event",
      event: {
        type: "turn/end",
        seq: 76,
        time: 44900,
        data: {
          turn: 1
        }
      }
    }
  ];

  // ../tmp/cannbot-native-replay/assembled-remote.ts
  var fixtureSource = JSON.stringify(fixture_default);
  var randomUUID = () => crypto.randomUUID();
  function createAssembledRemote(options = {}) {
    const fixture = JSON.parse(fixtureSource);
    const sessions2 = [];
    const workspaces = [{ ...structuredClone(fixture.workspace.value.items[0]), title: "Ascend C Flash", path: "/replay", sessionIds: [] }];
    const records = /* @__PURE__ */ new Map([[
      "fx-alpha",
      structuredClone(fixture.follow.records)
    ]]);
    const nextTurns = new Map([...records].map(([sessionId, sessionRecords]) => {
      let next = 0;
      for (const { event } of sessionRecords) {
        if (event.type !== "turn/start" || !isRecord(event.data)) continue;
        const turn = event.data["turn"];
        if (typeof turn === "number") next = Math.max(next, turn + 1);
      }
      return [sessionId, next];
    }));
    const attachments = /* @__PURE__ */ new Map([["fixture:image", structuredClone(fixture.attachment)]]);
    const stagedImages = /* @__PURE__ */ new Map();
    const blankSessionProjections = fixture.control.value.projections["fx-gamma"];
    if (blankSessionProjections === void 0) {
      throw new Error("assembled fixture: blank Session projections missing");
    }
    const activeReplays = /* @__PURE__ */ new Map();
    let nextSession = 1;
    const mock = RemoteMock.create().load(remoteDefaultResponses);
    mock.load({
      unary: {
        "settings/describe": ok({
          ...fixture.settingsDescribe.value,
          namespaces: [...fixture.settingsDescribe.value.namespaces, {
            ns: "cannbot-dsh",
            schema: {},
            value: { selections: [] },
            autoGenerate: false,
            applies: "live",
            secrets: [],
            revision: 0
          }, {
            ns: "ui-settings-general",
            schema: { type: "object", dict: { welcomeNoticeVersion: { type: "string" } } },
            value: { welcomeNoticeVersion: "2026-09-28.1" },
            autoGenerate: false,
            applies: "live",
            secrets: [],
            revision: 0
          }, {
            ns: "ui-settings",
            schema: { type: "object", dict: { enabled: { type: "boolean" } } },
            value: { enabled: options.developerTools ?? true },
            autoGenerate: false,
            applies: "live",
            secrets: [],
            revision: 0
          }]
        }),
        "settings/update": (ns, patch) => {
          if (typeof ns === "object") {
            patch = ns.patch;
            ns = ns.ns;
          }
          return ns === "cannbot-dsh" ? ok({ ns, value: { selections: patch?.selections ?? [] }, revision: 1 }) : ok({ ns, value: {}, revision: 1 });
        },
        "credentials/describe": structuredClone(fixture.credentialsDescribe),
        "session/modelCatalog": structuredClone(fixture.modelCatalog),
        "agentPresets/list": structuredClone(fixture.agentPresets),
        "commands/list": structuredClone(fixture.commands),
        "settings/openSettingsDocument": ok({ opened: true }),
        "terminal/list": ok([]),
        "skills/list": ok({ skills: [] }),
        "session/canOpenWorkspacePath": ok(true),
        "session/openWorkspacePath": ok({ opened: true }),
        "session/updateQueue": {
          ok: false,
          error: {
            code: "session/queue-item-not-found",
            message: "assembled fixture has no pending queue item",
            details: {}
          }
        },
        "session/cancel": (arg) => {
          const r = recordValue(arg, "request");
          const id = recordString(r, "sessionId");
          const active = activeReplays.get(id);
          if (!active) return ok({ accepted: false });
          activeReplays.delete(id);
          for (const timer of active.timers) clearTimeout(timer);
          const history2 = records.get(id);
          const stopped = eventOf(history2.length, "turn/end", { turn: active.turn, reason: { kind: "interrupted" } });
          history2.push(stopped);
          mock.streams.push("session/follow", stopped, follows(id));
          const summary = sessions2.find((x) => x.sessionId === id);
          if (summary) summary.running = false;
          mock.streams.push("$events", { type: "emit", event: "api-session/status", args: [id, false] });
          return ok({ accepted: true });
        }
      }
    });
    mock.stream("$events", (_args, stream) => {
      for (const frame of fixture.remoteEvents) stream.push(structuredClone(frame));
    });
    mock.stream("session/control", (_args, stream) => {
      stream.push(structuredClone(fixture.control));
    });
    mock.stream("job/list", (_args, stream) => {
      stream.push({ type: "rows", jobs: [] });
    });
    mock.stream("workspace/follow", (_args, stream) => {
      stream.push({
        type: "baseline",
        value: {
          items: structuredClone(workspaces),
          archivedSessionIds: structuredClone(fixture.workspace.value.archivedSessionIds),
          pinnedSessionIds: structuredClone(fixture.workspace.value.pinnedSessionIds)
        }
      });
    });
    mock.stream("session/follow", ([args], stream) => {
      const request = recordValue(args, "request");
      const sessionId = followedSessionId(request);
      if (sessionId === "fx-alpha") {
        stream.push(structuredClone(fixture.follow));
        return;
      }
      const summary = sessions2.find((candidate) => candidate.sessionId === sessionId);
      if (summary === void 0) throw new Error(`assembled fixture: no Session ${sessionId}`);
      const sessionRecords = records.get(sessionId) ?? [];
      stream.push({
        type: "snapshot",
        header: {
          version: 3,
          id: sessionId,
          createdAt: summary.updatedAt,
          cwd: summary.cwd,
          isSeeded: false
        },
        cursor: sessionRecords.at(-1)?.event.seq ?? -1,
        records: structuredClone(sessionRecords),
        hasMore: false,
        projections: structuredClone(blankSessionProjections),
        ...isAssistantStreamRequested(request) ? { assistantStream: { revision: 0 } } : {}
      });
    });
    mock.unary("$events/result", (result) => {
      const eventId = recordString(result, "eventId");
      mock.streams.push("$events", { type: "cancel", eventId });
      return ok(void 0);
    });
    mock.unary("session/page", (arg) => {
      const r = recordValue(arg, "request");
      return ok({ records: structuredClone((records.get(followedSessionId(r)) ?? []).filter((x) => x.event.seq <= (r.throughSeq ?? Infinity) && (r.beforeSeq === void 0 || x.event.seq < r.beforeSeq))), hasMore: false });
    });
    mock.unary("session/list", () => ok({ items: structuredClone(sessions2) }));
    mock.unary("schedule/catalog", () => ok([]));
    mock.unary("session/projections", (request) => {
      const sessionId = recordString(recordValue(request, "request"), "sessionId");
      const summary = sessions2.find((candidate) => candidate.sessionId === sessionId);
      return ok(structuredClone(summary?.projections ?? fixture.control.value.projections[sessionId] ?? null));
    });
    mock.unary("workspace/create", (request) => {
      const path = recordString(recordValue(request, "request"), "path");
      const existing = workspaces.find((workspace3) => workspace3.path === path);
      if (existing !== void 0) return ok({ workspace: structuredClone(existing), created: false });
      const now = (/* @__PURE__ */ new Date()).toISOString();
      const workspace2 = {
        workspaceId: `fx-ws-${String(workspaces.length + 1)}`,
        path,
        title: path.split("/").filter(Boolean).at(-1) ?? path,
        sessionIds: [],
        createdAt: now,
        updatedAt: now
      };
      workspaces.unshift(workspace2);
      mock.streams.push("workspace/follow", { type: "upsert", workspace: structuredClone(workspace2) });
      return ok({ workspace: structuredClone(workspace2), created: true });
    });
    mock.unary("session/create", (request) => {
      request = recordValue(request, "request");
      const requestedId = optionalRecordString(request, "sessionId");
      const sessionId = requestedId ?? `fx-${String(nextSession++)}`;
      const existing = sessions2.find((candidate) => candidate.sessionId === sessionId);
      if (existing !== void 0) return ok({ sessionId });
      const workspaceId = optionalRecordString(request, "workspaceId");
      const workspace2 = workspaces.find((candidate) => candidate.workspaceId === workspaceId);
      const cwd = workspace2?.path ?? optionalRecordString(request, "cwd") ?? "/tmp/fixture";
      const summary = {
        sessionId,
        updatedAt: Date.now(),
        running: false,
        blank: true,
        cwd,
        // The created Session is live on this fixture Host: its list block is
        // sequenced, like the block the real live registry would serve.
        projections: { kind: "sequenced", ...structuredClone(blankSessionProjections) }
      };
      sessions2.push(summary);
      records.set(sessionId, []);
      nextTurns.set(sessionId, 0);
      if (workspace2 !== void 0 && !workspace2.sessionIds.includes(sessionId)) {
        workspace2.sessionIds = [sessionId, ...workspace2.sessionIds];
        workspace2.updatedAt = (/* @__PURE__ */ new Date()).toISOString();
        mock.streams.push("workspace/follow", {
          type: "upsert",
          workspace: structuredClone(workspace2)
        });
      }
      mock.streams.push("$events", { type: "emit", event: "api-session/added", args: [structuredClone(summary)] });
      return ok({ sessionId });
    });
    mock.unary("session/attachment", (request) => {
      request = recordValue(request, "request");
      const attachment = recordValue(request, "attachment");
      const attachmentId = recordString(attachment, "attachmentId");
      const stored = attachments.get(attachmentId);
      if (stored !== void 0) return ok({ attachment, data: recordString(recordValue(stored, "value"), "data") });
      return {
        ok: false,
        error: {
          code: "session/attachment-invalid",
          message: `assembled fixture attachment ${attachmentId} is missing`,
          details: { reason: "ATTACHMENT_NOT_FOUND" }
        }
      };
    });
    mock.unary("session/prompt", (request) => {
      request = recordValue(request, "request");
      if (options.rejectPrompt === true) {
        return {
          ok: false,
          error: {
            code: "session/attachment-invalid",
            message: "assembled fixture: image side exceeds the deployment limit",
            details: { reason: "IMAGE_DIMENSION_TOO_LARGE" }
          }
        };
      }
      const sessionId = recordString(request, "sessionId");
      const requestId = recordString(request, "requestId");
      const sessionRecords = records.get(sessionId) ?? [];
      const summary = sessions2.find((candidate) => candidate.sessionId === sessionId);
      if (summary === void 0) throw new Error(`assembled fixture: no Session ${sessionId}`);
      const content = recordArray(request, "content").map((part) => {
        if (isRecord(part) && part.type === "file") {
          const image = stagedImages.get(recordString(part, "receiptId"));
          return image === void 0 ? part : { type: "image", attachment: image };
        }
        if (!isRecord(part) || part.type !== "image") return part;
        const attachmentId = `assembled:${randomUUID()}`;
        const data = recordString(part, "data");
        const attachment = {
          attachmentId,
          mediaType: recordString(part, "mediaType"),
          bytes: Math.max(1, Math.floor(data.length * 3 / 4)),
          width: 160,
          height: 90,
          ...optionalRecordString(part, "name") === void 0 ? {} : { name: optionalRecordString(part, "name") }
        };
        attachments.set(attachmentId, ok({ attachment, data }));
        return { type: "image", attachment };
      });
      const turn = nextTurns.get(sessionId) ?? 0;
      nextTurns.set(sessionId, turn + 1);
      summary.updatedAt = Date.now();
      summary.blank = false;
      if (!summary.running) {
        summary.running = true;
        mock.streams.push("$events", { type: "emit", event: "api-session/status", args: [sessionId, true] });
      }
      const turnEvent = eventOf(sessionRecords.length, "turn/start", { turn });
      const userEvent = eventOf(sessionRecords.length + 1, "user/message", {
        content,
        source: { kind: "user", rpcId: requestId },
        role: "user",
        id: randomUUID()
      }, "append");
      sessionRecords.push(turnEvent, userEvent);
      records.set(sessionId, sessionRecords);
      mock.streams.push("session/follow", turnEvent, follows(sessionId));
      mock.streams.push("session/follow", userEvent, follows(sessionId));
      const prompt = content.filter((p) => isRecord(p) && p.type === "text").map((p) => p.text).join(" ");
      const accept = /向量\s*(加法|相加)|vector[\s_-]+add|\badd\s*\u7b97\u5b50/i.test(prompt) && !/softmax|fp16|减法|乘法/i.test(prompt);
      const original = native_session_records_default.filter((x) => !["turn/start", "user/message"].includes(x.event.type));
      const replay2 = accept ? original : original.slice(-4);
      let last = replay2[0].event.time;
      const weights = replay2.map((x, i) => accept ? Math.min(Math.max(i ? x.event.time - replay2[i - 1].event.time : 550, 550), 1250) : Math.min(Math.max(i ? x.event.time - replay2[i - 1].event.time : 150, 140), 3500));
      const factor = accept ? 2e4 / weights.reduce((a, b) => a + b, 0) : 1;
      let delay = 0;
      let frameIndex = 0;
      const active = { turn, timers: [] };
      activeReplays.set(sessionId, active);
      for (const src of replay2) {
        const e = structuredClone(src);
        delay += weights[frameIndex++] * factor;
        if (!accept && e.event.type === "assistant/message") e.event.data.message.content = [{ type: "text", text: "\u5F53\u524D\u4E0D\u652F\u6301\u3002\u4EC5\u652F\u6301 FP32 \u5411\u91CF\u52A0\u6CD5\u6848\u4F8B\u56DE\u653E\u3002" }];
        active.timers.push(setTimeout(() => {
          if (activeReplays.get(sessionId) !== active) return;
          e.event.seq = sessionRecords.length;
          e.event.time = Date.now();
          if (e.event.type === "assistant/message") e.event.data.stream = [];
          if (e.event.type === "turn/end") e.event.data.reason = { kind: "completed" };
          if ("turn" in e.event.data) e.event.data.turn = turn;
          sessionRecords.push(e);
          mock.streams.push("session/follow", e, follows(sessionId));
          if (e.event.type === "turn/end") {
            activeReplays.delete(sessionId);
            summary.running = false;
            mock.streams.push("$events", { type: "emit", event: "api-session/status", args: [sessionId, false] });
          }
        }, delay));
      }
      return ok({ accepted: true });
    });
    mock.unary("commands/execute", (args) => {
      const line = optionalRecordString(args, "line") ?? "";
      const name = /^\/(\S+)/u.exec(line.trim())?.[1];
      if (name === void 0 || !["compact", "echo", "goal", "permission", "plan"].includes(name)) {
        return ok(void 0);
      }
      return ok({
        commandId: `assembled-command-${randomUUID()}`,
        result: {
          kind: "success",
          ...name === "echo" ? { text: line.replace(/^\/echo\s*/u, "") } : {}
        }
      });
    });
    const fileUpload = async (input, init) => {
      const url = new URL(String(input), "http://assembled.test/");
      const mediaType = url.searchParams.get("mediaType");
      if (!url.pathname.endsWith("/api/session/uploadFileBinary") || mediaType === null || !(init.body instanceof Blob)) {
        throw new Error(`assembled fixture: unexpected upload ${url.pathname}${url.search}`);
      }
      const bytes = new Uint8Array(await init.body.arrayBuffer());
      const name = url.searchParams.get("name");
      const image = {
        attachmentId: `assembled:${randomUUID()}`,
        mediaType,
        bytes: bytes.byteLength,
        width: 160,
        height: 90,
        ...name === null ? {} : { name }
      };
      attachments.set(image.attachmentId, ok({ attachment: image, data: btoa(String.fromCharCode(...bytes)) }));
      const receiptId = `assembled-receipt:${randomUUID()}`;
      stagedImages.set(receiptId, image);
      return new Response(JSON.stringify({ ok: true, value: { receiptId, image } }), { status: 200 });
    };
    return { mock, fileUpload };
  }
  function eventOf(seq, type, data, surfaceOp) {
    return {
      type: "event",
      event: {
        seq,
        time: Date.now(),
        type,
        data,
        ...surfaceOp === void 0 ? {} : { surfaceOp }
      }
    };
  }
  function follows(sessionId) {
    return ([args]) => followedSessionId(recordValue(args, "request")) === sessionId;
  }
  function followedSessionId(value) {
    if (!isRecord(value) || !isRecord(value.address)) throw new TypeError("assembled fixture follow request is invalid");
    return value.address.kind === "session" ? recordString(value.address, "sessionId") : recordString(value.address, "childSessionId");
  }
  function isAssistantStreamRequested(value) {
    return isRecord(value) && value.assistantStream === true;
  }
  function recordString(value, key) {
    const selected = isRecord(value) ? value[key] : void 0;
    if (typeof selected !== "string") throw new TypeError(`assembled fixture ${key} must be a string`);
    return selected;
  }
  function optionalRecordString(value, key) {
    const selected = isRecord(value) ? value[key] : void 0;
    if (selected === void 0) return void 0;
    if (typeof selected !== "string") throw new TypeError(`assembled fixture ${key} must be a string`);
    return selected;
  }
  function recordArray(value, key) {
    const selected = isRecord(value) ? value[key] : void 0;
    if (!Array.isArray(selected)) throw new TypeError(`assembled fixture ${key} must be an array`);
    return selected;
  }
  function recordValue(value, key) {
    if (!isRecord(value) || !(key in value)) throw new TypeError(`assembled fixture ${key} is missing`);
    return value[key];
  }
  function isRecord(value) {
    return typeof value === "object" && value !== null;
  }

  // ../tmp/cannbot-native-replay/transport-v3.ts
  var replay = createAssembledRemote();
  globalThis.__DSH_TRANSPORT__ = { rpc: replay.mock.rpc };
  var nativeFetch = globalThis.fetch.bind(globalThis);
  var workspace = { workspaceId: "fx-ws-fixture", path: "/replay", title: "Ascend C Flash", pluginId: "ops-direct-invoke-flash", sharedWithDeepSeek: false, sessionIds: [] };
  var sessions = [];
  globalThis.fetch = async (input, opts) => {
    const url = new URL(input instanceof Request ? input.url : input, document.baseURI);
    if (url.origin === location.origin && url.pathname.endsWith("/api/cannbot-dsh/content")) return Response.json({ phase: "ready", busy: false, plugins: [{ id: "ops-direct-invoke-flash", title: "Ascend C Flash", installed: true, enabled: true }] });
    if (url.origin === location.origin && url.pathname.endsWith("/api/cannbot-remote/servers")) return Response.json({ servers: [] });
    if (url.origin === location.origin && url.pathname.endsWith("/api/cannbot-dsh/workspaces")) {
      if (!opts?.body) return Response.json({ workspaces: [workspace], sessions });
      const d = JSON.parse(opts.body);
      if (d.action === "session" && d.workspaceId === workspace.workspaceId && typeof d.sessionId === "string") {
        const item = { sessionId: d.sessionId, workspaceId: workspace.workspaceId, archived: false };
        if (!workspace.sessionIds.includes(d.sessionId)) {
          workspace.sessionIds.push(d.sessionId);
          sessions.push(item);
        }
        return Response.json({ session: item });
      }
      return Response.json({ error: "offline-replay", message: "Offline replay only" }, { status: 405 });
    }
    return nativeFetch(input, opts);
  };
  if (!location.hash) history.replaceState(history.state, "", location.pathname + location.search + "#cannEmbed=1&cannMode=cannbot&cannWorkspace=fx-ws-fixture");
})();
