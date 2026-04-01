(function (global, factory) {
    typeof exports === 'object' && typeof module !== 'undefined' ? module.exports = factory() :
    typeof define === 'function' && define.amd ? define(factory) :
    (global = global || self, global.pluginSDK = factory());
}(this, (function () { 'use strict';

    var restCode = {
      errorCode: {
        FAIL: -1,
        //失败
        SUCCESS: 0,
        CALLNUMBER_EMPTY: 1001,
        //呼叫号码为空
        LOG_MESSAGE_EMPTY: 1002,
        //日志内容为空
        SUBJECT_CANNOT_EMPTY: 1003,
        SUBJECT_FORMAT_ERROR: 1004,
        INVITEE_LENGTH_EXCEED: 1005,
        INVITEE_FORMAT_ERROR: 1006,
        PARAM_ERROR: 1007,
        SESSION_TYPE_EMPTY: 1008,
        MEMBERLIST_ERROR: 1009,
        GROUP_CHAT_NAME_ERROR: 1010,
        SESSION_ID_EMPTY: 1011,
        MSGBODY_EMPTY: 1012,
        MSGBODY_LENGTH_EXCEED: 1013,
        PASSWORD_FORMAT_ERROR: 1014,
        HOSTCODE_FORMAT_ERROR: 1015,
        MEETING_NUM_ERROR: 1016,
        AGENDA_ERROR: 1017,
        EMAILREMINDTIME_ERROR: 1018,
        TIME_ERROR: 1019,
        MEMBER_LIST_EXCEED: 1020,
        DISK_FULL: 1021,
        USER_NOT_IN_SESSION: 1022,
        USER_CONFIG_EMPTY: 1023,
        //用户配置信息为空
        MEETING_NUM_EMPTY: 1024,
        SESSION_TYPE_ERROR: 1025,
        MEETING_PARTICIPANT_REACH_MAX: 1026,
        NO_AVAILABLE_RESOURCE: 1027,
        ITEM_ALREADY_ADD: 1028
      },
      errorMsg: {
        FAIL: "Operation fail",
        //失败
        SUCCESS: "Operation success",
        CALLNUMBER_EMPTY: "callNum cannot be empty",
        //呼叫号码为空
        LOG_MESSAGE_EMPTY: "Log message cannot be empty",
        //日志内容为空
        SUBJECT_CANNOT_EMPTY: "Meeting subject cannot be empty",
        SUBJECT_FORMAT_ERROR: "Meeting subject error",
        INVITEE_LENGTH_EXCEED: "Invitees count over the max",
        INVITEE_FORMAT_ERROR: "Invitees format error",
        PARAM_ERROR: "Param error",
        SESSION_TYPE_EMPTY: "Session type is empty",
        MEMBERLIST_ERROR: "Member list error",
        GROUP_CHAT_NAME_ERROR: "Group name error",
        SESSION_ID_EMPTY: "Session id is empty",
        MSGBODY_EMPTY: "Msg body is empty",
        MSGBODY_LENGTH_EXCEED: "Msg body too long",
        PASSWORD_FORMAT_ERROR: "Password format error",
        HOSTCODE_FORMAT_ERROR: "HostCode format error",
        MEETING_NUM_ERROR: "meetingNum error",
        AGENDA_ERROR: "Agenda error",
        EMAILREMINDTIME_ERROR: "Email remind time error",
        TIME_ERROR: "Time error",
        MEMBER_LIST_EXCEED: "Members count over the max",
        DISK_FULL: "Disk full",
        USER_NOT_IN_SESSION: "User has not this session",
        USER_CONFIG_EMPTY: "Config is empty",
        //用户配置信息为空
        MEETING_NUM_EMPTY: "MeetingNum is empty",
        SESSION_TYPE_ERROR: "Session type error",
        MEETING_PARTICIPANT_REACH_MAX: "The maximum limit of participants has been reached. ",
        NO_AVAILABLE_RESOURCE: "No available conference resource",
        ITEM_ALREADY_ADD: "This item has been added."
      }
    };

    var action = {
      //通话相关
      makeP2PAudioCall: "makeP2PAudioCall",
      makeP2PVideoCall: "makeP2PVideoCall",
      sendDTMF: "pluginSendDTMF",
      recvP2PIncomingCall: "recvP2PIncomingCall",
      answerP2PCall: "answerP2PCall",
      hangupP2PCall: "hangupP2PCall",
      rejectP2PCall: "rejectP2PCall",
      P2PCallCanceled: 'P2PCallCanceled',
      initP2PCall: 'initP2PCall',
      //日志模块
      logError: "logError",
      logLog: "logLog",
      logInfo: "logInfo",
      logWarn: "logWarn",
      //配置相关
      getUserConfig: "getUserConfig",
      addUserConfig: "addUserConfig",
      initPluginInfo: 'initPluginInfo',
      setPluginSignature: 'setPluginSignature',
      setPluginURLInterceptor: 'setPluginURLInterceptor',
      //窗口相关
      initPluginWindow: "initPluginWindow",
      hidePluginWin: "hidePluginWin",
      setDefaultWindow: "setDefaultWindow",
      closePluginWindow: "closePluginWindow",
      //监听事件
      addPluginEventLister: 'addPluginEventLister',
      //显示插件通知消息
      showNotificationMsg: 'showNotificationMsg',
      //隐藏插件通知
      hideNotificationMsg: 'hideNotificationMsg',
      //清除cookie
      clearCookie: 'pluginClearCookie',
      //插件操作事件回调
      pluginActionCallback: 'pluginActionCallback',
      //meeting相关
      quickStart: 'pluginQuickStartMeeting',
      scheduleMeeting: 'pluginScheduleMeeting',
      joinMeeting: 'pluginJoinMeeting',
      //聊天相关
      setChatFileAttach: 'setChatFileAttach',
      createSession: "pluginCreateSession",
      sendMsg: "pluginSendMsg",
      //通讯录相关
      getContactList: "pluginGetContactList"
    };

    function createCommonjsModule(fn, module) {
    	return module = { exports: {} }, fn(module, module.exports), module.exports;
    }

    var _global = createCommonjsModule(function (module) {
    // https://github.com/zloirock/core-js/issues/86#issuecomment-115759028
    var global = module.exports = typeof window != 'undefined' && window.Math == Math
      ? window : typeof self != 'undefined' && self.Math == Math ? self
      // eslint-disable-next-line no-new-func
      : Function('return this')();
    if (typeof __g == 'number') __g = global; // eslint-disable-line no-undef
    });

    var _core = createCommonjsModule(function (module) {
    var core = module.exports = { version: '2.6.12' };
    if (typeof __e == 'number') __e = core; // eslint-disable-line no-undef
    });
    var _core_1 = _core.version;

    var _isObject = function (it) {
      return typeof it === 'object' ? it !== null : typeof it === 'function';
    };

    var _anObject = function (it) {
      if (!_isObject(it)) throw TypeError(it + ' is not an object!');
      return it;
    };

    var _fails = function (exec) {
      try {
        return !!exec();
      } catch (e) {
        return true;
      }
    };

    // Thank's IE8 for his funny defineProperty
    var _descriptors = !_fails(function () {
      return Object.defineProperty({}, 'a', { get: function () { return 7; } }).a != 7;
    });

    var document = _global.document;
    // typeof document.createElement is 'object' in old IE
    var is = _isObject(document) && _isObject(document.createElement);
    var _domCreate = function (it) {
      return is ? document.createElement(it) : {};
    };

    var _ie8DomDefine = !_descriptors && !_fails(function () {
      return Object.defineProperty(_domCreate('div'), 'a', { get: function () { return 7; } }).a != 7;
    });

    // 7.1.1 ToPrimitive(input [, PreferredType])

    // instead of the ES6 spec version, we didn't implement @@toPrimitive case
    // and the second argument - flag - preferred type is a string
    var _toPrimitive = function (it, S) {
      if (!_isObject(it)) return it;
      var fn, val;
      if (S && typeof (fn = it.toString) == 'function' && !_isObject(val = fn.call(it))) return val;
      if (typeof (fn = it.valueOf) == 'function' && !_isObject(val = fn.call(it))) return val;
      if (!S && typeof (fn = it.toString) == 'function' && !_isObject(val = fn.call(it))) return val;
      throw TypeError("Can't convert object to primitive value");
    };

    var dP = Object.defineProperty;

    var f = _descriptors ? Object.defineProperty : function defineProperty(O, P, Attributes) {
      _anObject(O);
      P = _toPrimitive(P, true);
      _anObject(Attributes);
      if (_ie8DomDefine) try {
        return dP(O, P, Attributes);
      } catch (e) { /* empty */ }
      if ('get' in Attributes || 'set' in Attributes) throw TypeError('Accessors not supported!');
      if ('value' in Attributes) O[P] = Attributes.value;
      return O;
    };

    var _objectDp = {
    	f: f
    };

    var _propertyDesc = function (bitmap, value) {
      return {
        enumerable: !(bitmap & 1),
        configurable: !(bitmap & 2),
        writable: !(bitmap & 4),
        value: value
      };
    };

    var _hide = _descriptors ? function (object, key, value) {
      return _objectDp.f(object, key, _propertyDesc(1, value));
    } : function (object, key, value) {
      object[key] = value;
      return object;
    };

    var hasOwnProperty = {}.hasOwnProperty;
    var _has = function (it, key) {
      return hasOwnProperty.call(it, key);
    };

    var id = 0;
    var px = Math.random();
    var _uid = function (key) {
      return 'Symbol('.concat(key === undefined ? '' : key, ')_', (++id + px).toString(36));
    };

    var _shared = createCommonjsModule(function (module) {
    var SHARED = '__core-js_shared__';
    var store = _global[SHARED] || (_global[SHARED] = {});

    (module.exports = function (key, value) {
      return store[key] || (store[key] = value !== undefined ? value : {});
    })('versions', []).push({
      version: _core.version,
      mode:  'global',
      copyright: '© 2020 Denis Pushkarev (zloirock.ru)'
    });
    });

    var _functionToString = _shared('native-function-to-string', Function.toString);

    var _redefine = createCommonjsModule(function (module) {
    var SRC = _uid('src');

    var TO_STRING = 'toString';
    var TPL = ('' + _functionToString).split(TO_STRING);

    _core.inspectSource = function (it) {
      return _functionToString.call(it);
    };

    (module.exports = function (O, key, val, safe) {
      var isFunction = typeof val == 'function';
      if (isFunction) _has(val, 'name') || _hide(val, 'name', key);
      if (O[key] === val) return;
      if (isFunction) _has(val, SRC) || _hide(val, SRC, O[key] ? '' + O[key] : TPL.join(String(key)));
      if (O === _global) {
        O[key] = val;
      } else if (!safe) {
        delete O[key];
        _hide(O, key, val);
      } else if (O[key]) {
        O[key] = val;
      } else {
        _hide(O, key, val);
      }
    // add fake Function#toString for correct work wrapped methods / constructors with methods like LoDash isNative
    })(Function.prototype, TO_STRING, function toString() {
      return typeof this == 'function' && this[SRC] || _functionToString.call(this);
    });
    });

    var _aFunction = function (it) {
      if (typeof it != 'function') throw TypeError(it + ' is not a function!');
      return it;
    };

    // optional / simple context binding

    var _ctx = function (fn, that, length) {
      _aFunction(fn);
      if (that === undefined) return fn;
      switch (length) {
        case 1: return function (a) {
          return fn.call(that, a);
        };
        case 2: return function (a, b) {
          return fn.call(that, a, b);
        };
        case 3: return function (a, b, c) {
          return fn.call(that, a, b, c);
        };
      }
      return function (/* ...args */) {
        return fn.apply(that, arguments);
      };
    };

    var PROTOTYPE = 'prototype';

    var $export = function (type, name, source) {
      var IS_FORCED = type & $export.F;
      var IS_GLOBAL = type & $export.G;
      var IS_STATIC = type & $export.S;
      var IS_PROTO = type & $export.P;
      var IS_BIND = type & $export.B;
      var target = IS_GLOBAL ? _global : IS_STATIC ? _global[name] || (_global[name] = {}) : (_global[name] || {})[PROTOTYPE];
      var exports = IS_GLOBAL ? _core : _core[name] || (_core[name] = {});
      var expProto = exports[PROTOTYPE] || (exports[PROTOTYPE] = {});
      var key, own, out, exp;
      if (IS_GLOBAL) source = name;
      for (key in source) {
        // contains in native
        own = !IS_FORCED && target && target[key] !== undefined;
        // export native or passed
        out = (own ? target : source)[key];
        // bind timers to global for call from export context
        exp = IS_BIND && own ? _ctx(out, _global) : IS_PROTO && typeof out == 'function' ? _ctx(Function.call, out) : out;
        // extend global
        if (target) _redefine(target, key, out, type & $export.U);
        // export
        if (exports[key] != out) _hide(exports, key, exp);
        if (IS_PROTO && expProto[key] != out) expProto[key] = out;
      }
    };
    _global.core = _core;
    // type bitmap
    $export.F = 1;   // forced
    $export.G = 2;   // global
    $export.S = 4;   // static
    $export.P = 8;   // proto
    $export.B = 16;  // bind
    $export.W = 32;  // wrap
    $export.U = 64;  // safe
    $export.R = 128; // real proto method for `library`
    var _export = $export;

    var toString = {}.toString;

    var _cof = function (it) {
      return toString.call(it).slice(8, -1);
    };

    // fallback for non-array-like ES3 and non-enumerable old V8 strings

    // eslint-disable-next-line no-prototype-builtins
    var _iobject = Object('z').propertyIsEnumerable(0) ? Object : function (it) {
      return _cof(it) == 'String' ? it.split('') : Object(it);
    };

    // 7.2.1 RequireObjectCoercible(argument)
    var _defined = function (it) {
      if (it == undefined) throw TypeError("Can't call method on  " + it);
      return it;
    };

    // 7.1.13 ToObject(argument)

    var _toObject = function (it) {
      return Object(_defined(it));
    };

    // 7.1.4 ToInteger
    var ceil = Math.ceil;
    var floor = Math.floor;
    var _toInteger = function (it) {
      return isNaN(it = +it) ? 0 : (it > 0 ? floor : ceil)(it);
    };

    // 7.1.15 ToLength

    var min = Math.min;
    var _toLength = function (it) {
      return it > 0 ? min(_toInteger(it), 0x1fffffffffffff) : 0; // pow(2, 53) - 1 == 9007199254740991
    };

    // 7.2.2 IsArray(argument)

    var _isArray = Array.isArray || function isArray(arg) {
      return _cof(arg) == 'Array';
    };

    var _wks = createCommonjsModule(function (module) {
    var store = _shared('wks');

    var Symbol = _global.Symbol;
    var USE_SYMBOL = typeof Symbol == 'function';

    var $exports = module.exports = function (name) {
      return store[name] || (store[name] =
        USE_SYMBOL && Symbol[name] || (USE_SYMBOL ? Symbol : _uid)('Symbol.' + name));
    };

    $exports.store = store;
    });

    var SPECIES = _wks('species');

    var _arraySpeciesConstructor = function (original) {
      var C;
      if (_isArray(original)) {
        C = original.constructor;
        // cross-realm fallback
        if (typeof C == 'function' && (C === Array || _isArray(C.prototype))) C = undefined;
        if (_isObject(C)) {
          C = C[SPECIES];
          if (C === null) C = undefined;
        }
      } return C === undefined ? Array : C;
    };

    // 9.4.2.3 ArraySpeciesCreate(originalArray, length)


    var _arraySpeciesCreate = function (original, length) {
      return new (_arraySpeciesConstructor(original))(length);
    };

    // 0 -> Array#forEach
    // 1 -> Array#map
    // 2 -> Array#filter
    // 3 -> Array#some
    // 4 -> Array#every
    // 5 -> Array#find
    // 6 -> Array#findIndex





    var _arrayMethods = function (TYPE, $create) {
      var IS_MAP = TYPE == 1;
      var IS_FILTER = TYPE == 2;
      var IS_SOME = TYPE == 3;
      var IS_EVERY = TYPE == 4;
      var IS_FIND_INDEX = TYPE == 6;
      var NO_HOLES = TYPE == 5 || IS_FIND_INDEX;
      var create = $create || _arraySpeciesCreate;
      return function ($this, callbackfn, that) {
        var O = _toObject($this);
        var self = _iobject(O);
        var f = _ctx(callbackfn, that, 3);
        var length = _toLength(self.length);
        var index = 0;
        var result = IS_MAP ? create($this, length) : IS_FILTER ? create($this, 0) : undefined;
        var val, res;
        for (;length > index; index++) if (NO_HOLES || index in self) {
          val = self[index];
          res = f(val, index, O);
          if (TYPE) {
            if (IS_MAP) result[index] = res;   // map
            else if (res) switch (TYPE) {
              case 3: return true;             // some
              case 5: return val;              // find
              case 6: return index;            // findIndex
              case 2: result.push(val);        // filter
            } else if (IS_EVERY) return false; // every
          }
        }
        return IS_FIND_INDEX ? -1 : IS_SOME || IS_EVERY ? IS_EVERY : result;
      };
    };

    var _strictMethod = function (method, arg) {
      return !!method && _fails(function () {
        // eslint-disable-next-line no-useless-call
        arg ? method.call(null, function () { /* empty */ }, 1) : method.call(null);
      });
    };

    var $map = _arrayMethods(1);

    _export(_export.P + _export.F * !_strictMethod([].map, true), 'Array', {
      // 22.1.3.15 / 15.4.4.19 Array.prototype.map(callbackfn [, thisArg])
      map: function map(callbackfn /* , thisArg */) {
        return $map(this, callbackfn, arguments[1]);
      }
    });

    // to indexed object, toObject with fallback for non-array-like ES3 strings


    var _toIobject = function (it) {
      return _iobject(_defined(it));
    };

    var max = Math.max;
    var min$1 = Math.min;
    var _toAbsoluteIndex = function (index, length) {
      index = _toInteger(index);
      return index < 0 ? max(index + length, 0) : min$1(index, length);
    };

    // false -> Array#indexOf
    // true  -> Array#includes



    var _arrayIncludes = function (IS_INCLUDES) {
      return function ($this, el, fromIndex) {
        var O = _toIobject($this);
        var length = _toLength(O.length);
        var index = _toAbsoluteIndex(fromIndex, length);
        var value;
        // Array#includes uses SameValueZero equality algorithm
        // eslint-disable-next-line no-self-compare
        if (IS_INCLUDES && el != el) while (length > index) {
          value = O[index++];
          // eslint-disable-next-line no-self-compare
          if (value != value) return true;
        // Array#indexOf ignores holes, Array#includes - not
        } else for (;length > index; index++) if (IS_INCLUDES || index in O) {
          if (O[index] === el) return IS_INCLUDES || index || 0;
        } return !IS_INCLUDES && -1;
      };
    };

    var $indexOf = _arrayIncludes(false);
    var $native = [].indexOf;
    var NEGATIVE_ZERO = !!$native && 1 / [1].indexOf(1, -0) < 0;

    _export(_export.P + _export.F * (NEGATIVE_ZERO || !_strictMethod($native)), 'Array', {
      // 22.1.3.11 / 15.4.4.14 Array.prototype.indexOf(searchElement [, fromIndex])
      indexOf: function indexOf(searchElement /* , fromIndex = 0 */) {
        return NEGATIVE_ZERO
          // convert -0 to +0
          ? $native.apply(this, arguments) || 0
          : $indexOf(this, searchElement, arguments[1]);
      }
    });

    /*
     * 用于监听事件定义
     *
     */
    function Event() {
      /* 开发给使用者的注册事件 */
      this.handlers = {
        onError: [],
        // 发生错误时的通知事件
        recvMessage: [] //收到消息时的通知事件

      };
    }

    Event.prototype.on = function (eventName, handle) {
      if (typeof handle === 'function') {
        if (!this.handlers.hasOwnProperty(eventName)) {
          this.handlers[eventName] = [];
        }

        this.handlers[eventName].push(handle);
      } else {
        throw new Error('Provided parameter is not a function');
      }
    }; //请慎用


    Event.prototype.once = function (eventName, handle) {
      var _this = this;

      var wrapFunc = function wrapFunc() {
        //创建一个wrapFanc函数实现单次调用后停止监听
        handle.apply(void 0, arguments); //执行wrapFunc

        _this.off(eventName, wrapFunc); //后停止监听事件

      };

      this.on(eventName, wrapFunc); //注册监听wrapFunc事件
    };

    Event.prototype.trigger = function (eventName) {
      for (var _len = arguments.length, params = new Array(_len > 1 ? _len - 1 : 0), _key = 1; _key < _len; _key++) {
        params[_key - 1] = arguments[_key];
      }

      if (!this.handlers.hasOwnProperty(eventName)) return; //事件队列依次执行

      this.handlers[eventName].map(function (handle) {
        handle.apply(void 0, params);
      });
    };

    Event.prototype.off = function (eventName, handle) {
      if (!this.handlers.hasOwnProperty(eventName)) return;

      if (typeof handle === 'undefined') {
        this.handlers[eventName] = [];
        return;
      }

      var index = this.handlers[eventName].indexOf(handle);

      if (index !== -1) {
        this.handlers[eventName].splice(index, 1);
      }
    };

    var event = {}; //实例化Event

    var eventInstance = undefined;

    event.getEventInstance = function () {
      if (!eventInstance) {
        eventInstance = new Event();
      }

      return eventInstance;
    };

    /*
    用于定义前端事件监听
     */
    var pluginEvent = {}; //通话相关
    //接收p2p语音通话消息

    pluginEvent.onRecvIncomingCall = "onRecvP2PIncomingCall"; //接听音频通话

    pluginEvent.onAnswerCall = "onAnswerP2PCall"; //挂断通话

    pluginEvent.onHangupCall = "onHangupP2PCall"; //拒接音频通话

    pluginEvent.onRejectCall = "onRejectP2PCall"; //取消来电

    pluginEvent.onCallCanceled = "onP2PCallCanceled"; //wave发起呼叫

    pluginEvent.onInitCall = "onInitP2PCall"; //窗口相关
    //窗口初始化成功

    pluginEvent.onInitPluginWindow = 'onInitPluginWindowOk'; //插件信息相关

    pluginEvent.onInitPluginInfo = 'onInitPluginInfoOk';

    // 7.2.9 SameValue(x, y)
    var _sameValue = Object.is || function is(x, y) {
      // eslint-disable-next-line no-self-compare
      return x === y ? x !== 0 || 1 / x === 1 / y : x != x && y != y;
    };

    // getting tag from 19.1.3.6 Object.prototype.toString()

    var TAG = _wks('toStringTag');
    // ES3 wrong here
    var ARG = _cof(function () { return arguments; }()) == 'Arguments';

    // fallback for IE11 Script Access Denied error
    var tryGet = function (it, key) {
      try {
        return it[key];
      } catch (e) { /* empty */ }
    };

    var _classof = function (it) {
      var O, T, B;
      return it === undefined ? 'Undefined' : it === null ? 'Null'
        // @@toStringTag case
        : typeof (T = tryGet(O = Object(it), TAG)) == 'string' ? T
        // builtinTag case
        : ARG ? _cof(O)
        // ES3 arguments fallback
        : (B = _cof(O)) == 'Object' && typeof O.callee == 'function' ? 'Arguments' : B;
    };

    var builtinExec = RegExp.prototype.exec;

     // `RegExpExec` abstract operation
    // https://tc39.github.io/ecma262/#sec-regexpexec
    var _regexpExecAbstract = function (R, S) {
      var exec = R.exec;
      if (typeof exec === 'function') {
        var result = exec.call(R, S);
        if (typeof result !== 'object') {
          throw new TypeError('RegExp exec method returned something other than an Object or null');
        }
        return result;
      }
      if (_classof(R) !== 'RegExp') {
        throw new TypeError('RegExp#exec called on incompatible receiver');
      }
      return builtinExec.call(R, S);
    };

    // 21.2.5.3 get RegExp.prototype.flags

    var _flags = function () {
      var that = _anObject(this);
      var result = '';
      if (that.global) result += 'g';
      if (that.ignoreCase) result += 'i';
      if (that.multiline) result += 'm';
      if (that.unicode) result += 'u';
      if (that.sticky) result += 'y';
      return result;
    };

    var nativeExec = RegExp.prototype.exec;
    // This always refers to the native implementation, because the
    // String#replace polyfill uses ./fix-regexp-well-known-symbol-logic.js,
    // which loads this file before patching the method.
    var nativeReplace = String.prototype.replace;

    var patchedExec = nativeExec;

    var LAST_INDEX = 'lastIndex';

    var UPDATES_LAST_INDEX_WRONG = (function () {
      var re1 = /a/,
          re2 = /b*/g;
      nativeExec.call(re1, 'a');
      nativeExec.call(re2, 'a');
      return re1[LAST_INDEX] !== 0 || re2[LAST_INDEX] !== 0;
    })();

    // nonparticipating capturing group, copied from es5-shim's String#split patch.
    var NPCG_INCLUDED = /()??/.exec('')[1] !== undefined;

    var PATCH = UPDATES_LAST_INDEX_WRONG || NPCG_INCLUDED;

    if (PATCH) {
      patchedExec = function exec(str) {
        var re = this;
        var lastIndex, reCopy, match, i;

        if (NPCG_INCLUDED) {
          reCopy = new RegExp('^' + re.source + '$(?!\\s)', _flags.call(re));
        }
        if (UPDATES_LAST_INDEX_WRONG) lastIndex = re[LAST_INDEX];

        match = nativeExec.call(re, str);

        if (UPDATES_LAST_INDEX_WRONG && match) {
          re[LAST_INDEX] = re.global ? match.index + match[0].length : lastIndex;
        }
        if (NPCG_INCLUDED && match && match.length > 1) {
          // Fix browsers whose `exec` methods don't consistently return `undefined`
          // for NPCG, like IE8. NOTE: This doesn' work for /(.?)?/
          // eslint-disable-next-line no-loop-func
          nativeReplace.call(match[0], reCopy, function () {
            for (i = 1; i < arguments.length - 2; i++) {
              if (arguments[i] === undefined) match[i] = undefined;
            }
          });
        }

        return match;
      };
    }

    var _regexpExec = patchedExec;

    _export({
      target: 'RegExp',
      proto: true,
      forced: _regexpExec !== /./.exec
    }, {
      exec: _regexpExec
    });

    var SPECIES$1 = _wks('species');

    var REPLACE_SUPPORTS_NAMED_GROUPS = !_fails(function () {
      // #replace needs built-in support for named groups.
      // #match works fine because it just return the exec results, even if it has
      // a "grops" property.
      var re = /./;
      re.exec = function () {
        var result = [];
        result.groups = { a: '7' };
        return result;
      };
      return ''.replace(re, '$<a>') !== '7';
    });

    var SPLIT_WORKS_WITH_OVERWRITTEN_EXEC = (function () {
      // Chrome 51 has a buggy "split" implementation when RegExp#exec !== nativeExec
      var re = /(?:)/;
      var originalExec = re.exec;
      re.exec = function () { return originalExec.apply(this, arguments); };
      var result = 'ab'.split(re);
      return result.length === 2 && result[0] === 'a' && result[1] === 'b';
    })();

    var _fixReWks = function (KEY, length, exec) {
      var SYMBOL = _wks(KEY);

      var DELEGATES_TO_SYMBOL = !_fails(function () {
        // String methods call symbol-named RegEp methods
        var O = {};
        O[SYMBOL] = function () { return 7; };
        return ''[KEY](O) != 7;
      });

      var DELEGATES_TO_EXEC = DELEGATES_TO_SYMBOL ? !_fails(function () {
        // Symbol-named RegExp methods call .exec
        var execCalled = false;
        var re = /a/;
        re.exec = function () { execCalled = true; return null; };
        if (KEY === 'split') {
          // RegExp[@@split] doesn't call the regex's exec method, but first creates
          // a new one. We need to return the patched regex when creating the new one.
          re.constructor = {};
          re.constructor[SPECIES$1] = function () { return re; };
        }
        re[SYMBOL]('');
        return !execCalled;
      }) : undefined;

      if (
        !DELEGATES_TO_SYMBOL ||
        !DELEGATES_TO_EXEC ||
        (KEY === 'replace' && !REPLACE_SUPPORTS_NAMED_GROUPS) ||
        (KEY === 'split' && !SPLIT_WORKS_WITH_OVERWRITTEN_EXEC)
      ) {
        var nativeRegExpMethod = /./[SYMBOL];
        var fns = exec(
          _defined,
          SYMBOL,
          ''[KEY],
          function maybeCallNative(nativeMethod, regexp, str, arg2, forceStringMethod) {
            if (regexp.exec === _regexpExec) {
              if (DELEGATES_TO_SYMBOL && !forceStringMethod) {
                // The native String method already delegates to @@method (this
                // polyfilled function), leasing to infinite recursion.
                // We avoid it by directly calling the native @@method method.
                return { done: true, value: nativeRegExpMethod.call(regexp, str, arg2) };
              }
              return { done: true, value: nativeMethod.call(str, regexp, arg2) };
            }
            return { done: false };
          }
        );
        var strfn = fns[0];
        var rxfn = fns[1];

        _redefine(String.prototype, KEY, strfn);
        _hide(RegExp.prototype, SYMBOL, length == 2
          // 21.2.5.8 RegExp.prototype[@@replace](string, replaceValue)
          // 21.2.5.11 RegExp.prototype[@@split](string, limit)
          ? function (string, arg) { return rxfn.call(string, this, arg); }
          // 21.2.5.6 RegExp.prototype[@@match](string)
          // 21.2.5.9 RegExp.prototype[@@search](string)
          : function (string) { return rxfn.call(string, this); }
        );
      }
    };

    // @@search logic
    _fixReWks('search', 1, function (defined, SEARCH, $search, maybeCallNative) {
      return [
        // `String.prototype.search` method
        // https://tc39.github.io/ecma262/#sec-string.prototype.search
        function search(regexp) {
          var O = defined(this);
          var fn = regexp == undefined ? undefined : regexp[SEARCH];
          return fn !== undefined ? fn.call(regexp, O) : new RegExp(regexp)[SEARCH](String(O));
        },
        // `RegExp.prototype[@@search]` method
        // https://tc39.github.io/ecma262/#sec-regexp.prototype-@@search
        function (regexp) {
          var res = maybeCallNative($search, regexp, this);
          if (res.done) return res.value;
          var rx = _anObject(regexp);
          var S = String(this);
          var previousLastIndex = rx.lastIndex;
          if (!_sameValue(previousLastIndex, 0)) rx.lastIndex = 0;
          var result = _regexpExecAbstract(rx, S);
          if (!_sameValue(rx.lastIndex, previousLastIndex)) rx.lastIndex = previousLastIndex;
          return result === null ? -1 : result.index;
        }
      ];
    });

    var f$1 = {}.propertyIsEnumerable;

    var _objectPie = {
    	f: f$1
    };

    var gOPD = Object.getOwnPropertyDescriptor;

    var f$2 = _descriptors ? gOPD : function getOwnPropertyDescriptor(O, P) {
      O = _toIobject(O);
      P = _toPrimitive(P, true);
      if (_ie8DomDefine) try {
        return gOPD(O, P);
      } catch (e) { /* empty */ }
      if (_has(O, P)) return _propertyDesc(!_objectPie.f.call(O, P), O[P]);
    };

    var _objectGopd = {
    	f: f$2
    };

    // Works with __proto__ only. Old v8 can't work with null proto objects.
    /* eslint-disable no-proto */


    var check = function (O, proto) {
      _anObject(O);
      if (!_isObject(proto) && proto !== null) throw TypeError(proto + ": can't set as prototype!");
    };
    var _setProto = {
      set: Object.setPrototypeOf || ('__proto__' in {} ? // eslint-disable-line
        function (test, buggy, set) {
          try {
            set = _ctx(Function.call, _objectGopd.f(Object.prototype, '__proto__').set, 2);
            set(test, []);
            buggy = !(test instanceof Array);
          } catch (e) { buggy = true; }
          return function setPrototypeOf(O, proto) {
            check(O, proto);
            if (buggy) O.__proto__ = proto;
            else set(O, proto);
            return O;
          };
        }({}, false) : undefined),
      check: check
    };

    var setPrototypeOf = _setProto.set;
    var _inheritIfRequired = function (that, target, C) {
      var S = target.constructor;
      var P;
      if (S !== C && typeof S == 'function' && (P = S.prototype) !== C.prototype && _isObject(P) && setPrototypeOf) {
        setPrototypeOf(that, P);
      } return that;
    };

    var shared = _shared('keys');

    var _sharedKey = function (key) {
      return shared[key] || (shared[key] = _uid(key));
    };

    var arrayIndexOf = _arrayIncludes(false);
    var IE_PROTO = _sharedKey('IE_PROTO');

    var _objectKeysInternal = function (object, names) {
      var O = _toIobject(object);
      var i = 0;
      var result = [];
      var key;
      for (key in O) if (key != IE_PROTO) _has(O, key) && result.push(key);
      // Don't enum bug & hidden keys
      while (names.length > i) if (_has(O, key = names[i++])) {
        ~arrayIndexOf(result, key) || result.push(key);
      }
      return result;
    };

    // IE 8- don't enum bug keys
    var _enumBugKeys = (
      'constructor,hasOwnProperty,isPrototypeOf,propertyIsEnumerable,toLocaleString,toString,valueOf'
    ).split(',');

    // 19.1.2.7 / 15.2.3.4 Object.getOwnPropertyNames(O)

    var hiddenKeys = _enumBugKeys.concat('length', 'prototype');

    var f$3 = Object.getOwnPropertyNames || function getOwnPropertyNames(O) {
      return _objectKeysInternal(O, hiddenKeys);
    };

    var _objectGopn = {
    	f: f$3
    };

    var _stringWs = '\x09\x0A\x0B\x0C\x0D\x20\xA0\u1680\u180E\u2000\u2001\u2002\u2003' +
      '\u2004\u2005\u2006\u2007\u2008\u2009\u200A\u202F\u205F\u3000\u2028\u2029\uFEFF';

    var space = '[' + _stringWs + ']';
    var non = '\u200b\u0085';
    var ltrim = RegExp('^' + space + space + '*');
    var rtrim = RegExp(space + space + '*$');

    var exporter = function (KEY, exec, ALIAS) {
      var exp = {};
      var FORCE = _fails(function () {
        return !!_stringWs[KEY]() || non[KEY]() != non;
      });
      var fn = exp[KEY] = FORCE ? exec(trim) : _stringWs[KEY];
      if (ALIAS) exp[ALIAS] = fn;
      _export(_export.P + _export.F * FORCE, 'String', exp);
    };

    // 1 -> String#trimLeft
    // 2 -> String#trimRight
    // 3 -> String#trim
    var trim = exporter.trim = function (string, TYPE) {
      string = String(_defined(string));
      if (TYPE & 1) string = string.replace(ltrim, '');
      if (TYPE & 2) string = string.replace(rtrim, '');
      return string;
    };

    var _stringTrim = exporter;

    // 19.1.2.14 / 15.2.3.14 Object.keys(O)



    var _objectKeys = Object.keys || function keys(O) {
      return _objectKeysInternal(O, _enumBugKeys);
    };

    var _objectDps = _descriptors ? Object.defineProperties : function defineProperties(O, Properties) {
      _anObject(O);
      var keys = _objectKeys(Properties);
      var length = keys.length;
      var i = 0;
      var P;
      while (length > i) _objectDp.f(O, P = keys[i++], Properties[P]);
      return O;
    };

    var document$1 = _global.document;
    var _html = document$1 && document$1.documentElement;

    // 19.1.2.2 / 15.2.3.5 Object.create(O [, Properties])



    var IE_PROTO$1 = _sharedKey('IE_PROTO');
    var Empty = function () { /* empty */ };
    var PROTOTYPE$1 = 'prototype';

    // Create object with fake `null` prototype: use iframe Object with cleared prototype
    var createDict = function () {
      // Thrash, waste and sodomy: IE GC bug
      var iframe = _domCreate('iframe');
      var i = _enumBugKeys.length;
      var lt = '<';
      var gt = '>';
      var iframeDocument;
      iframe.style.display = 'none';
      _html.appendChild(iframe);
      iframe.src = 'javascript:'; // eslint-disable-line no-script-url
      // createDict = iframe.contentWindow.Object;
      // html.removeChild(iframe);
      iframeDocument = iframe.contentWindow.document;
      iframeDocument.open();
      iframeDocument.write(lt + 'script' + gt + 'document.F=Object' + lt + '/script' + gt);
      iframeDocument.close();
      createDict = iframeDocument.F;
      while (i--) delete createDict[PROTOTYPE$1][_enumBugKeys[i]];
      return createDict();
    };

    var _objectCreate = Object.create || function create(O, Properties) {
      var result;
      if (O !== null) {
        Empty[PROTOTYPE$1] = _anObject(O);
        result = new Empty();
        Empty[PROTOTYPE$1] = null;
        // add "__proto__" for Object.getPrototypeOf polyfill
        result[IE_PROTO$1] = O;
      } else result = createDict();
      return Properties === undefined ? result : _objectDps(result, Properties);
    };

    var gOPN = _objectGopn.f;
    var gOPD$1 = _objectGopd.f;
    var dP$1 = _objectDp.f;
    var $trim = _stringTrim.trim;
    var NUMBER = 'Number';
    var $Number = _global[NUMBER];
    var Base = $Number;
    var proto = $Number.prototype;
    // Opera ~12 has broken Object#toString
    var BROKEN_COF = _cof(_objectCreate(proto)) == NUMBER;
    var TRIM = 'trim' in String.prototype;

    // 7.1.3 ToNumber(argument)
    var toNumber = function (argument) {
      var it = _toPrimitive(argument, false);
      if (typeof it == 'string' && it.length > 2) {
        it = TRIM ? it.trim() : $trim(it, 3);
        var first = it.charCodeAt(0);
        var third, radix, maxCode;
        if (first === 43 || first === 45) {
          third = it.charCodeAt(2);
          if (third === 88 || third === 120) return NaN; // Number('+0x1') should be NaN, old V8 fix
        } else if (first === 48) {
          switch (it.charCodeAt(1)) {
            case 66: case 98: radix = 2; maxCode = 49; break; // fast equal /^0b[01]+$/i
            case 79: case 111: radix = 8; maxCode = 55; break; // fast equal /^0o[0-7]+$/i
            default: return +it;
          }
          for (var digits = it.slice(2), i = 0, l = digits.length, code; i < l; i++) {
            code = digits.charCodeAt(i);
            // parseInt parses a string to a first unavailable symbol
            // but ToNumber should return NaN if a string contains unavailable symbols
            if (code < 48 || code > maxCode) return NaN;
          } return parseInt(digits, radix);
        }
      } return +it;
    };

    if (!$Number(' 0o1') || !$Number('0b1') || $Number('+0x1')) {
      $Number = function Number(value) {
        var it = arguments.length < 1 ? 0 : value;
        var that = this;
        return that instanceof $Number
          // check on 1..constructor(foo) case
          && (BROKEN_COF ? _fails(function () { proto.valueOf.call(that); }) : _cof(that) != NUMBER)
            ? _inheritIfRequired(new Base(toNumber(it)), that, $Number) : toNumber(it);
      };
      for (var keys = _descriptors ? gOPN(Base) : (
        // ES3:
        'MAX_VALUE,MIN_VALUE,NaN,NEGATIVE_INFINITY,POSITIVE_INFINITY,' +
        // ES6 (in case, if modules with ES6 Number statics required before):
        'EPSILON,isFinite,isInteger,isNaN,isSafeInteger,MAX_SAFE_INTEGER,' +
        'MIN_SAFE_INTEGER,parseFloat,parseInt,isInteger'
      ).split(','), j = 0, key; keys.length > j; j++) {
        if (_has(Base, key = keys[j]) && !_has($Number, key)) {
          dP$1($Number, key, gOPD$1(Base, key));
        }
      }
      $Number.prototype = proto;
      proto.constructor = $Number;
      _redefine(_global, NUMBER, $Number);
    }

    //id
    var nLogNum = 1; //日志序列号
    //debug:1, log:2, info:3, warn:4, error:5

    function setLogLevel(level) {
      return level.toLowerCase() === "error" ? 5 : level.toLowerCase() === "warn" ? 4 : level.toLowerCase() === "info" ? 3 : level.toLowerCase() === "log" ? 2 : 1;
    }

    var nLogLevel = setLogLevel("log");

    function webrtc_log_debug(s_msg) {
      if (nLogLevel <= 1) {
        if (nLogNum > 100000) {
          nLogNum = 1;
        }

        var logtime = "[" + nLogNum++ + "]";
        window.console.debug(logtime + " " + s_msg);
      }
    }

    function webrtc_log_log(s_msg) {
      if (nLogLevel <= 2) {
        if (nLogNum > 100000) {
          nLogNum = 1;
        }

        var logtime = "[" + nLogNum++ + "]";
        window.console.log(logtime + " " + s_msg);
      }
    }

    function webrtc_log_info(s_msg) {
      if (nLogLevel <= 3) {
        if (nLogNum > 100000) {
          nLogNum = 1;
        }

        var logtime = "[" + nLogNum++ + "]";
        window.console.info(logtime + " " + s_msg);
      }
    }

    function webrtc_log_warn(s_msg) {
      if (nLogLevel <= 4) {
        if (nLogNum > 100000) {
          nLogNum = 1;
        }

        var logtime = "[" + nLogNum++ + "]";
        window.console.warn(logtime + " " + s_msg);
      }
    }

    function webrtc_log_error(s_msg) {
      if (nLogLevel <= 5) {
        if (nLogNum > 100000) {
          nLogNum = 1;
        }

        var logtime = "[" + nLogNum++ + "]";
        window.console.error(logtime + " " + s_msg);
      }
    }
    /**
     * 提供一个日志调用对象，按模块名打印，模块名为空，按原先方式打印日志
     * 实例化示例：<打印方法msg参数允许为undefined>
     * var log = new Log.WebrtcLogger(sMoudleName);
     * new Log.WebrtcLogger().warn("rrrrr");
     * log.info(msg);/log.warn();/log.error();
     */
    //


    var Logger = function Logger(sMoudleName) {
      var sMoudleName = sMoudleName;

      function wrapMsg(sMsg) {
        //若sMsg为undefined，则内容也为undefined
        //			if(sMsg == undefined){
        //				sMsg = "";
        //			}
        if (sMoudleName == undefined || sMoudleName == "") {
          sMsg = sMsg;
        } else {
          sMsg = "[" + sMoudleName + "] " + sMsg;
        }

        return sMsg;
      } //开放给外部调用的日志打印方法


      this.debug = function (sLogMsg) {
        var sNewLogMsg = wrapMsg(sLogMsg);
        webrtc_log_debug(sNewLogMsg);
      };

      this.log = function (sLogMsg) {
        var sNewLogMsg = wrapMsg(sLogMsg);
        webrtc_log_log(sNewLogMsg);
      };

      this.info = function (sLogMsg) {
        var sNewLogMsg = wrapMsg(sLogMsg);
        webrtc_log_info(sNewLogMsg);
      };

      this.warn = function (sLogMsg) {
        var sNewLogMsg = wrapMsg(sLogMsg);
        webrtc_log_warn(sNewLogMsg);
      };

      this.error = function (sLogMsg) {
        var sNewLogMsg = wrapMsg(sLogMsg);
        webrtc_log_error(sNewLogMsg);
      };
    };
    /**
     * 兼容debug模式
     * @param sMoudleName
     */


    var log = {};

    if (window.debug) {
      log.debug = window.debug('pluginSDK:DEBUG');
      log.log = window.debug('pluginSDK:INFO');
      log.info = window.debug('pluginSDK:INFO');
      log.warn = window.debug('pluginSDK:WARN');
      log.error = window.debug('pluginSDK:ERROR');
    } else {
      var logger = new Logger("pluginSDK");

      log.debug = function (msg) {
        return logger.debug(msg);
      };

      log.log = function (msg) {
        return logger.log(msg);
      };

      log.info = function (msg) {
        return logger.info(msg);
      };

      log.warn = function (msg) {
        return logger.warn(msg);
      };

      log.error = function (msg) {
        return logger.error(msg);
      };
    }

    var common = {};

    common.getPluginId = function () {
      var _window$location = window.location,
          _window$location$sear = _window$location.search,
          search = _window$location$sear === void 0 ? '' : _window$location$sear,
          origin = _window$location.origin,
          pathname = _window$location.pathname;
      var query = new URLSearchParams(search);

      if (query && origin === "file://" && pathname.indexOf('index.html') !== -1) {
        var pluginId = query.get('pluginId');

        if (pluginId === null) {
          return '';
        }

        return pluginId;
      }

      return '';
    };

    common.getWaveDesktopVersion = function () {
      var _window$location2 = window.location,
          _window$location2$sea = _window$location2.search,
          search = _window$location2$sea === void 0 ? '' : _window$location2$sea,
          origin = _window$location2.origin,
          pathname = _window$location2.pathname;
      var query = new URLSearchParams(search);

      if (query && origin === "file://" && pathname.indexOf('index.html') !== -1) {
        var desktopVersion = query.get('desktopVersion');

        if (desktopVersion === null) {
          return '';
        }

        return desktopVersion;
      }

      return '';
    };

    common.getIsWaveSupportPlugin = function () {
      var _window$location3 = window.location,
          _window$location3$sea = _window$location3.search,
          search = _window$location3$sea === void 0 ? '' : _window$location3$sea,
          origin = _window$location3.origin,
          pathname = _window$location3.pathname;
      var query = new URLSearchParams(search);

      if (query && origin === "file://" && pathname.indexOf('index.html') !== -1) {
        var isWaveSupportPlugin = query.get('isWaveSupportPlugin');

        if (isWaveSupportPlugin) {
          isWaveSupportPlugin = isNaN(Number(isWaveSupportPlugin)) ? 1 : Number(isWaveSupportPlugin);
        }

        if (isWaveSupportPlugin === null) {
          return undefined;
        }

        return isWaveSupportPlugin;
      }

      return 1;
    };
    /**
     * 获取wave支持的最小sdk 版本
     * @returns {string}
     */


    common.getMinSDKVersion = function () {
      var _window$location4 = window.location,
          _window$location4$sea = _window$location4.search,
          search = _window$location4$sea === void 0 ? '' : _window$location4$sea,
          origin = _window$location4.origin,
          pathname = _window$location4.pathname;
      var query = new URLSearchParams(search);

      if (query && origin === "file://" && pathname.indexOf('index.html') !== -1) {
        var minSDKVersion = query.get('sdkMinV');

        if (minSDKVersion === null) {
          return '';
        }

        return minSDKVersion;
      }

      return '';
    };
    /**
     * 获取wave支持的最大sdk 版本
     * @returns {string}
     */


    common.getMaxSDKVersion = function () {
      var _window$location5 = window.location,
          _window$location5$sea = _window$location5.search,
          search = _window$location5$sea === void 0 ? '' : _window$location5$sea,
          origin = _window$location5.origin,
          pathname = _window$location5.pathname;
      var query = new URLSearchParams(search);

      if (query && origin === "file://" && pathname.indexOf('index.html') !== -1) {
        var maxSDKVersion = query.get('sdkMaxV');

        if (maxSDKVersion === null) {
          return '';
        }

        return maxSDKVersion;
      }

      return '';
    };

    var pluginRequestCallback = new Array(); //请求回调，用于服务器返回数据处理

    /**
     *
     * @type {{PrivateChat: number, GroupChat: number}}
     */

    var SessionType = {
      PRIVATECHAT: 1,
      //私聊
      GROUPCHAT: 2,
      //群聊
      CONFHELPER: 3 //会议小助手

    };
    var MsgType = {
      //1表示普通文本消息，2表示文件，3表示图片，4表示系统通知, 5合并转发, 7会议小助手消息,8语音消息
      TEXT: 1,
      FILE: 2,
      IMAGE: 3,
      NOTIFICATION: 4,
      MERGERFWD: 5,
      CONFNOTIFICATION: 7,
      VOICEMSG: 8
    };
    /**
     * 系统通知类型
     * 1表示有新用户用户进群，2可表示有用户离开群，3表示解散群，4表示更改群名, 5表示被踢除群聊, 6表示群主转移，7表示消息撤回,8表示编辑已发送的消息
     * 9、表情回复，10、撤回表情回复，11、是否允许群成员邀请新成员
     * @type {{joinSession: number, leaveSession: number, deleteSession: number, updateGroupName: number}}
     */

    var MsgSubType = {
      JOINGROUP: 1,
      LEAVEGROUP: 2,
      DISMISSGROUP: 3,
      UPDATEGROUPNAME: 4,
      KICKEDOUTGROUP: 5,
      OWNERTRANSFER: 6,
      DELETEMSG: 7,
      EDITMSG: 8,
      EMOJIREPLY: 9,
      EMOJIREPLYREVORK: 10,
      INVITEMEMBER: 11
    };
    /**
     * 工作状态
     * @type {{None: number, InMeeting: number, OnBusinessTrip: number, Telecommuting: number, SickLeave: number, OnHoliday: number, custom: number}}
     */

    var WorkStatus = {
      NONE: 0,
      //无
      INMEETING: 1,
      //会议中
      ONBUSINESSTRIP: 2,
      //出差中
      TELECOMMUTING: 3,
      //远程办公中
      SICKLEAVE: 4,
      //生病请假中
      ONHOLIDAY: 5,
      //休假中
      CUSTOMIZE: 6 //自定义

    };
    /**
     * 分机状态
     * @type {{Idle: '空闲', InUse: '忙碌', Unavailable: '离线', dnd:'勿扰',Away:'离开'}}
     */

    var ExtensionStatus = {
      IDLE: 'Idle',
      INUSE: 'Inuse',
      UNAVAILABLE: 'Unavailable',
      DND: 'Dnd',
      AWAY: 'Away'
    };
    var MeetingCycleType = {
      DAILY: "DAILY",
      WEEKLY: "WEEKLY",
      MONTHLY: "MONTHLY"
    };
    var currentSDKVersion = "1.0.4";

    /*
    常量
    */
    var requestCallback = new Array(); //请求回调，用于服务器返回数据处理

    var _require = require('electron'),
        ipcRenderer = _require.ipcRenderer;
    var electronEvent = {};
    var pluginWinInfo = {};
    /**
     *@param {action: '操作',data:'json格式'}
     */

    electronEvent.postMsgToWave = function (action, data) {
      if (action && data) {
        data.action = action;
        data.pluginId = pluginWinInfo.pluginId;
        ipcRenderer.send('plugin-window-message', 'pluginWindow', data);
      }
    };
    /**
     * 收到主进程的监听事件
     */


    ipcRenderer.on('postMessage2pluginWindow', function (event$1, data) {
      // console.log('plugin recv data from wave:' + JSON.stringify(data))
      if (data.action === action.initPluginWindow) {
        //初始化插件
        pluginWinInfo.pluginId = data.pluginId; // pluginWinInfo.pluginWin = data.pluginWindow;

        pluginWinInfo.userConfig = data.userConfig; //用户配置信息

        var initData = {
          //pluginId: data.pluginId,
          userConfig: data.userConfig,
          pluginPath: data.pluginPath,
          originModule: data.originModule //用于Google Driver插件，不同模块，不同模块插件页面展现不一致

        };
        pluginWinInfo.sessionId = data.sessionId; //用户Google Driver，打开时切换session导致取文件错误

        pluginWinInfo.desktopVersion = data.desktopVersion;
        pluginWinInfo.isWaveSupportPlugin = data.isWaveSupportPlugin;
        pluginWinInfo.minSDKVersion = data.supportSDKMinVersion;
        pluginWinInfo.maxSDKVersion = data.supportSDKMaxVersion;
        event.getEventInstance().trigger(pluginEvent.onInitPluginWindow, initData);
      } else if (data.action === action.initPluginInfo) {
        if (data.pluginId) {
          pluginWinInfo.pluginId = data.pluginId;
        }

        if (data.sessionId) {
          pluginWinInfo.sessionId = data.sessionId; //用户Google Driver，打开时切换session导致取文件错误
        }

        if (data.desktopVersion) {
          pluginWinInfo.desktopVersion = data.desktopVersion;
        }

        if (data.isWaveSupportPlugin !== undefined) {
          pluginWinInfo.isWaveSupportPlugin = data.isWaveSupportPlugin;
        }

        if (data.supportSDKMinVersion !== undefined) {
          pluginWinInfo.minSDKVersion = data.supportSDKMinVersion;
        }

        if (data.supportSDKMaxVersion) {
          pluginWinInfo.maxSDKVersion = data.supportSDKMaxVersion;
        }

        var _initData = {
          originModule: data.originModule,
          //用于Google Driver插件，不同模块，不同模块插件页面展现不一致
          pluginPath: data.pluginPath
        };
        event.getEventInstance().trigger(pluginEvent.onInitPluginInfo, _initData);
      } else if (data.action === action.recvP2PIncomingCall) {
        //收到来电
        var callMsg = {
          callType: data.callType,
          callNum: data.callNum
        };
        event.getEventInstance().trigger(pluginEvent.onRecvIncomingCall, callMsg);
      } else if (data.action === action.answerP2PCall) {
        var _callMsg = {
          callType: data.callType,
          callNum: data.callNum
        };
        event.getEventInstance().trigger(pluginEvent.onAnswerCall, _callMsg);
      } else if (data.action === action.hangupP2PCall) {
        var _callMsg2 = {
          callType: data.callType,
          callNum: data.callNum,
          callStartTimeStamp: data.callStartTimeStamp,
          callEndTimeStamp: data.callEndTimeStamp,
          callDirection: data.callDirection
        };
        event.getEventInstance().trigger(pluginEvent.onHangupCall, _callMsg2);
      } else if (data.action === action.rejectP2PCall) {
        var _callMsg3 = {
          callType: data.callType,
          callNum: data.callNum
        };
        event.getEventInstance().trigger(pluginEvent.onRejectCall, _callMsg3);
      } else if (data.action === action.P2PCallCanceled) {
        var _callMsg4 = {
          callNum: data.callNum
        };
        event.getEventInstance().trigger(pluginEvent.onCallCanceled, _callMsg4);
      } else if (data.action === action.initP2PCall) {
        var _callMsg5 = {
          callNum: data.callNum,
          callType: data.callType
        };
        event.getEventInstance().trigger(pluginEvent.onInitCall, _callMsg5);
      } else if (data.action === action.pluginActionCallback) {
        //处理插件操作事件的回调
        handlerRecvEventCallback(data);
      }
    });

    electronEvent.getPluginInfo = function () {
      return JSON.parse(JSON.stringify(pluginWinInfo));
    };
    /**
     * 修改配置
     * @param data {{userConfig: *}}
     */


    electronEvent.updatePluginConfig = function (data) {
      if (data.userConfig !== undefined) {
        pluginWinInfo.userConfig = data.userConfig;
      }

      if (data.pluginId) {
        pluginWinInfo.pluginId = data.pluginId;
      }
    };
    /**
     * 初始话pluginId
     */


    electronEvent.initPluginId = function () {
      var pluginId = common.getPluginId();

      if (pluginId) {
        pluginWinInfo.pluginId = pluginId;
      }

      var isWaveSupportPlugin = common.getIsWaveSupportPlugin();

      if (isWaveSupportPlugin !== undefined) {
        pluginWinInfo.isWaveSupportPlugin = isWaveSupportPlugin;
      }

      var desktopVersion = common.getWaveDesktopVersion();

      if (desktopVersion) {
        pluginWinInfo.desktopVersion = desktopVersion;
      }

      var minSDKVersion = common.getMinSDKVersion();

      if (minSDKVersion) {
        pluginWinInfo.minSDKVersion = minSDKVersion;
      }

      var maxSDKVersion = common.getMaxSDKVersion();

      if (maxSDKVersion) {
        pluginWinInfo.maxSDKVersion = maxSDKVersion;
      }
    };
    /**
     * 加载js时从url中获取pluginId;
     */


    electronEvent.initPluginId();

    function handlerRecvEventCallback(data) {
      for (var i = 0; i < pluginRequestCallback.length; i++) {
        if (data.requestId === pluginRequestCallback[i].requestId) {
          break;
        }
      }

      var response = {
        errorCode: data.errorCode,
        errorMsg: data.errorMsg
      };

      if (data.errorCode === restCode.errorCode.SUCCESS) {
        response.data = data.data;
      }

      if (pluginRequestCallback[i]) {
        pluginRequestCallback[i].callback(response);
      }

      requestCallback.splice(i, 1);
    }

    /*
    将插件绑定的事件传递给wave
     */
    var bindEvent = {};

    bindEvent.on = function (eventName, handle) {
      var data = {
        eventName: eventName
      };
      event.getEventInstance().on(eventName, handle);
      electronEvent.postMsgToWave(action.addPluginEventLister, data);
    };

    bindEvent.off = function (eventName, handle) {
      event.getEventInstance().off(eventName, handle);
    };

    bindEvent.once = function (eventName, handle) {
      event.getEventInstance().once(eventName, handle);
    };

    /*
    窗口相关
     */
    var pluginWin = {};
    /**
     * 关闭窗口
     * @type {boolean}
     */

    pluginWin.closeWindow = function () {
      electronEvent.postMsgToWave(action.closePluginWindow, {});
    };
    /**
     * 插件窗口隐藏
     */


    pluginWin.hideWindow = function () {
      electronEvent.postMsgToWave(action.hidePluginWin, {});
    };
    /**
     * 使用默认窗口并显示
     * @param data {width:'宽度, int',height:'高度, int',
     * winX:'窗口相对于屏幕左侧的偏移量(如果使用了Y,此必选), int',winY:'窗口相对于屏幕顶端的偏移量(如果使用了X,此必选), int',
     * center:'是否居中（与X,Y互斥）',show:'是否显示'}
     */


    pluginWin.setDefaultWindow = function (data) {
      if (data.winY && !data.winX || !data.winY && data.winX) {
        return;
      }

      var param = {};

      if (data.width) {
        param.width = data.width;
      }

      if (data.height) {
        param.height = data.height;
      }

      if (data.winX) {
        param.winX = data.winX;
      }

      if (data.winY) {
        param.winY = data.winY;
      }

      if (data.center !== undefined && typeof data.center !== 'boolean' || data.show !== undefined && typeof data.show !== 'boolean') {
        return;
      }

      if (data.center !== undefined) {
        param.center = data.center;
      }

      if (data.show !== undefined) {
        param.show = data.show;
      }

      electronEvent.postMsgToWave(action.setDefaultWindow, data);
    };
    /**
     * 使用Wave通知窗口并显示
     * @param data {notificationBody:'通知消息内容体(html节点)'}
     *
     */


    pluginWin.showNotificationWindow = function (data) {
      if (!data && !data.notificationBody) {
        return;
      }

      electronEvent.postMsgToWave(action.showNotificationMsg, data);
    };
    /**
     * 隐藏插件通知
     */


    pluginWin.hideNotificationWindow = function () {
      electronEvent.postMsgToWave(action.hideNotificationMsg, {});
    };

    /*
    通话相关
     */
    var calls = {};
    /**
     * 音频通话
     * @param data {callNumber:'呼叫号码'}
     * @param callback
     */

    calls.makeP2PAudioCall = function (data, callback) {
      if (typeof callback !== "function") {
        console.error('makeP2PAudioCall callback not function');
        return;
      }

      if (!data || !data.callNumber) {
        callback({
          errorCode: restCode.errorCode.CALLNUMBER_EMPTY,
          errorMsg: restCode.errorMsg.CALLNUMBER_EMPTY
        });
        return false;
      }

      var jsonBody = {
        callNumber: data.callNumber
      };
      electronEvent.postMsgToWave(action.makeP2PAudioCall, jsonBody);
      callback({
        errorCode: restCode.errorCode.SUCCESS,
        errorMsg: restCode.errorMsg.SUCCESS
      });
    };
    /**
     * 视频通话
     * @param data {callNumber:'呼叫号码'}
     * @param callback
     */


    calls.makeP2PVideoCall = function (data, callback) {
      if (typeof callback !== "function") {
        console.error('makeP2PVideoCall callback not function');
        return;
      }

      if (!data || !data.callNumber) {
        callback({
          errorCode: restCode.errorCode.CALLNUMBER_EMPTY,
          errorMsg: restCode.errorMsg.CALLNUMBER_EMPTY
        });
        return false;
      }

      var jsonBody = {
        callNumber: data.callNumber
      };
      electronEvent.postMsgToWave(action.makeP2PVideoCall, jsonBody);
      callback({
        errorCode: restCode.errorCode.SUCCESS,
        errorMsg: restCode.errorMsg.SUCCESS
      });
    };
    /**
     * 发送DTMF
     * @param data {digits: 按键值 数字类型的字符串 string， 必填}
     * @param callback
     */


    calls.sendDTMF = function (data, callback) {
      if (typeof callback !== "function") {
        console.error('sendDTMF callback not function');
        return;
      }

      if (!data || !data.digits) {
        callback({
          errorCode: restCode.errorCode.PARAM_EMPTY,
          errorMsg: restCode.errorMsg.PARAM_EMPTY
        });
        return false;
      }

      var dtmfContent = {
        digits: data.digits
      };
      electronEvent.postMsgToWave(action.sendDTMF, dtmfContent);
      callback({
        errorCode: restCode.errorCode.SUCCESS,
        errorMsg: restCode.errorMsg.SUCCESS
      });
    };

    var callExt = {};
    /**
     * 音频通话
     * @param data {callNumber:"呼叫号码,String, 必填, 如果为跨域分机则需要带cloud im配置前缀"}
     * @param callback
     */

    callExt.makeP2PAudioCall = function (data, callback) {
      calls.makeP2PAudioCall(data, callback);
    };
    /**
     * 视频通话
     * @param data {callNumber:"呼叫号码,String, 必填, 如果为跨域分机则需要带cloud im配置前缀"}
     * @param callback
     */


    callExt.makeP2PVideoCall = function (data, callback) {
      calls.makeP2PVideoCall(data, callback);
    };
    /**
     * 发送DTMF
     * @param data {digits: 按键值 数字类型的字符串(string)}
     * @param callback
     */


    callExt.sendDTMF = function (data, callback) {
      calls.sendDTMF(data, callback);
    };

    /*
    日志模块
     */
    var logger$1 = {};
    /**
     * log 打印
     * @param data
     */

    logger$1.log = function (data) {
      if (!data) {
        callback({
          errorCode: restCode.errorCode.LOG_MESSAGE_EMPTY,
          errorMsg: restCode.errorMsg.LOG_MESSAGE_EMPTY
        });
        return false;
      }

      var jsonBody = {
        message: data
      };
      electronEvent.postMsgToWave(action.logLog, jsonBody);
    };
    /**
     * info日志 打印
     * @param data
     */


    logger$1.info = function (data) {
      console.log('recv message from plugin:' + data);

      if (!data) {
        callback({
          errorCode: restCode.errorCode.LOG_MESSAGE_EMPTY,
          errorMsg: restCode.errorMsg.LOG_MESSAGE_EMPTY
        });
        return false;
      }

      var jsonBody = {
        message: data
      };
      electronEvent.postMsgToWave(action.logInfo, jsonBody);
    };
    /**
     * warn日志 打印
     * @param data
     */


    logger$1.warn = function (data) {
      if (!data) {
        callback({
          errorCode: restCode.errorCode.LOG_MESSAGE_EMPTY,
          errorMsg: restCode.errorMsg.LOG_MESSAGE_EMPTY
        });
        return false;
      }

      var jsonBody = {
        message: data
      };
      electronEvent.postMsgToWave(action.logWarn, jsonBody);
    };
    /**
     * warn日志 打印
     * @param data
     */


    logger$1.error = function (data) {
      if (!data) {
        callback({
          errorCode: restCode.errorCode.LOG_MESSAGE_EMPTY,
          errorMsg: restCode.errorMsg.LOG_MESSAGE_EMPTY
        });
        return false;
      }

      var jsonBody = {
        message: data
      };
      electronEvent.postMsgToWave(action.logError, jsonBody);
    };

    var logExt = {};
    /**
     * 打印错误日志
     * @param message:'日志'(String)
     */

    logExt.error = function (message) {
      logger$1.error(message);
    };
    /**
     * 打印LOG日志
     * @param message:'日志'(String)
     */


    logExt.log = function (message) {
      logger$1.log(message);
    };
    /**
     * 打印INFO日志
     * @param message:'日志'(String)
     */


    logExt.info = function (message) {
      logger$1.info(message);
    };
    /**
     * 打印warn日志
     * @param message:'日志'(String)
     */


    logExt.warn = function (message) {
      logger$1.warn(message);
    };

    /*
    用户配置信息存取
     */
    var userConfig = {};
    /**
     * 存用户信息
     * @param data {config:'配置信息'(json)}
     */

    userConfig.addUserConfig = function (data, callback) {
      if (!data || !data.userConfig) {
        callback({
          errorCode: restCode.errorCode.USER_CONFIG_EMPTY,
          errorMsg: restCode.errorMsg.USER_CONFIG_EMPTY
        });
        return false;
      }

      var message = {
        userConfig: data.userConfig
      }; //更新内存中的配置

      electronEvent.updatePluginConfig(data);
      electronEvent.postMsgToWave(action.addUserConfig, message);
      callback({
        errorCode: restCode.errorCode.SUCCESS,
        errorMsg: restCode.errorMsg.SUCCESS
      });
    };
    /**
     * 取用户信息
     * @param data {config:'配置信息'(json)}
     */


    userConfig.getUserConfig = function (callback) {
      // electronEvent.postMsgToWave(action.getUserConfig, message)
      var pluginInfo = electronEvent.getPluginInfo();

      if (pluginInfo.userConfig) {
        callback({
          errorCode: restCode.errorCode.SUCCESS,
          data: pluginInfo.userConfig
        });
        return false;
      } else {
        if (!pluginInfo.pluginId) {
          callback({
            errorCode: restCode.errorCode.FAIL
          });
          return;
        }

        getUserConfigFromMain(function (result) {
          if (result && result.data && result.data.userConfig) {
            electronEvent.updatePluginConfig({
              userConfig: result.data.userConfig
            });
            callback({
              errorCode: restCode.errorCode.SUCCESS,
              data: result.data.userConfig
            });
          } else {
            callback({
              errorCode: restCode.errorCode.FAIL
            });
          }
        });
      }
    };

    function getUserConfigFromMain(callback) {
      var userConfigParam = {
        requestId: new Date().getTime()
      };
      var request = {
        meetingParam: userConfigParam,
        requestId: userConfigParam.requestId,
        callback: callback
      };
      pluginRequestCallback.push(request);
      electronEvent.postMsgToWave(action.getUserConfig, userConfigParam);
    }
    /**
     * 设置插件签名
     * @param data {signature:'签名字符串'}
     */


    userConfig.setPluginSignature = function (data) {
      if (!data || !data.signature) {
        console.error('plugin signature empty');
        return;
      }

      var message = {
        signature: data.signature
      };
      electronEvent.postMsgToWave(action.setPluginSignature, message);
    };

    var userConfigExt = {};
    /**
     * 获取用户信息
     * @param callback
     */

    userConfigExt.getUserConfig = function (callback) {
      userConfig.getUserConfig(callback);
    };
    /**
     * 存用户信息
     * @param data {userConfig:'配置信息'(json)}
     */


    userConfigExt.addUserConfig = function (data, callback) {
      userConfig.addUserConfig(data, callback);
    };
    /**
     * 设置插件签名
     * @param data {signature:'签名字符串'}
     */


    userConfigExt.setPluginSignature = function (data) {
      userConfig.setPluginSignature(data);
    };

    var meeting = {};
    /**
     * 即时会议
     * @param {subject:'主题（string, 120位,必填）, invitees:'userObject数组, 受邀者不超过300人，选填'}
     * invitees:[{memberExtension:'分机号', email:"邮箱"}]
     * memberExtension 与email必填一个,可同时带
     * invitees没有受邀者带空数组或不带此属性
     */

    meeting.quickStart = function (data, callback) {
      if (typeof callback !== "function") {
        console.error('quickStart callback not function');
        return;
      }

      var pluginInfo = electronEvent.getPluginInfo();

      if (!pluginInfo.pluginId) {
        callback({
          errorCode: restCode.errorCode.FAIL
        });
        return;
      }

      if (!data || !data.subject) {
        callback({
          errorCode: restCode.errorCode.SUBJECT_CANNOT_EMPTY,
          errorMsg: restCode.errorMsg.SUBJECT_CANNOT_EMPTY
        });
        return;
      }

      var meetingParam = {
        requestId: new Date().getTime(),
        subject: data.subject,
        invitees: data.invitees
      };
      var request = {
        meetingParam: meetingParam,
        requestId: meetingParam.requestId,
        callback: callback
      };
      pluginRequestCallback.push(request);
      electronEvent.postMsgToWave(action.quickStart, meetingParam);
    };
    /**
     * 预约会议
     * @param data {
    * subject:'主题,120,string,必填',
    * password:'密码，int，4-10位，选填',
    * hostCode:'主持码，int, 4-10位,选填，如不填则随机生成',
    * agenda:'会议议程，string,500位,选填',
    * meetingType: '会议类型，0:随机会议号，1:固定会议号；当为1时，meetingNum必填'
        * meetingNum:"固定会议室号码,int, 选填，不填则为随机会议号",
    * autoCallInvite:"是否自动呼叫受邀者(0/1,选填，默认0)",
    * allowParticipantsInvite:"是否允许参会者邀请,0/1,int,选填,默认0",
    * emailRemindTime:'会前邮件提醒，值范围5-120, int, 选填,默认值为60',
    * startTime:'会议开始时间, Unix时间戳（毫秒数）, int',
    * endTime: '会议结束时间, Unix时间戳（毫秒数）, int',
    * cycle:'循环会议规则, 不带则非循环会议, 值：DAILY, WEEKLY, MONTHLY',
    * invitees:'受邀者, 对象数组，受邀者不超过300人，选填，如果为空则以当前wave的登录账号为主持人'
     * }
     * invitees:[{memberExtension:'分机号', email:"邮箱", isHost:'是否为主持人'}]
     * memberExtension 与email必填一个,可同时带
     * invitees没有受邀者带空数组或不带此属性
     *
     * @param callback
     */


    meeting.schedule = function (data, callback) {
      if (typeof callback !== "function") {
        console.log('callback not function');
        return;
      }

      var pluginInfo = electronEvent.getPluginInfo();

      if (!pluginInfo.pluginId) {
        callback({
          errorCode: restCode.errorCode.FAIL
        });
        return;
      }

      if (!data || !data.subject) {
        callback({
          errorCode: restCode.errorCode.SUBJECT_CANNOT_EMPTY,
          errorMsg: restCode.errorMsg.SUBJECT_CANNOT_EMPTY
        });
        return;
      }

      var meetingParam = {
        requestId: new Date().getTime(),
        subject: data.subject,
        password: data.password,
        hostCode: data.hostCode,
        agenda: data.agenda,
        meetingType: data.meetingType,
        meetingNum: data.meetingNum,
        autoCallInvite: data.autoCallInvite,
        allowParticipantsInvite: data.allowParticipantsInvite,
        emailRemindTime: data.emailRemindTime,
        startTime: data.startTime,
        endTime: data.endTime,
        cycle: data.cycle,
        invitees: data.invitees
      };
      var request = {
        meetingParam: meetingParam,
        requestId: meetingParam.requestId,
        callback: callback
      };
      pluginRequestCallback.push(request);
      electronEvent.postMsgToWave(action.scheduleMeeting, meetingParam);
    };
    /**
     * 加入会议接口
     * @param data {meetingNum:'会议号， string, 必填', password:'会议密码，int, 选填'}
     */


    meeting.join = function (data, callback) {
      if (typeof callback !== "function") {
        console.error('join meeting callback not function');
        return;
      }

      var pluginInfo = electronEvent.getPluginInfo();

      if (!pluginInfo.pluginId) {
        callback({
          errorCode: restCode.errorCode.FAIL
        });
        return;
      }

      if (!data || !data.meetingNum) {
        callback({
          errorCode: restCode.errorCode.MEETING_NUM_ERROR,
          errorMsg: restCode.errorMsg.MEETING_NUM_ERROR
        });
        return false;
      }

      var jsonBody = {
        meetingNum: data.meetingNum,
        password: data.password
      };
      electronEvent.postMsgToWave(action.joinMeeting, jsonBody);
      callback({
        errorCode: restCode.errorCode.SUCCESS,
        errorMsg: restCode.errorMsg.SUCCESS
      });
    };

    var meetingExt = {};
    /**
     * 即时会议
     * @param {subject:'主题（string, 120位,必填）, invitees:'userObject数组, 受邀者不超过300人，选填'}
     * invitees:[{memberExtension:'分机号', email:"邮箱"}]
     * memberExtension 与email必填一个,可同时带
     * invitees没有受邀者带空数组或不带此属性
     */

    meetingExt.quickStart = function (data, callback) {
      meeting.quickStart(data, callback);
    };
    /**
    * 预约会议
    * @param data {
    * subject:'主题,120,string,必填',
    * password:'密码，int，4-10位，选填',
    * hostCode:'主持码，int, 4-10位,选填，如不填则随机生成',
    * agenda:'会议议程，string,500位,选填',
    * meetingType: '会议类型，0:随机会议号，1:固定会议号；当为1时，meetingNum必填'
    * meetingNum:"固定会议室号码,int, 选填，不填则为随机会议号",
    * autoCallInvite:"是否自动呼叫受邀者(0/1,选填，默认0)",
    * allowParticipantsInvite:"是否允许参会者邀请,0/1,int,选填,默认0",
    * emailRemindTime:'会前邮件提醒，值范围5-120, int, 选填,默认值为60',
    * startTime:'会议开始时间, Unix时间戳（毫秒数）, int',
    * endTime: '会议结束时间, Unix时间戳（毫秒数）, int',
    * cycle:'循环会议规则, 不带则非循环会议, 值：DAILY, WEEKLY, MONTHLY',
    * invitees:'受邀者, 对象数组，受邀者不超过300人，选填，如果为空则以当前wave的登录账号为主持人'
     * }
     * invitees:[{memberExtension:'分机号', email:"邮箱", isHost:'是否为主持人'}]
     * memberExtension 与email必填一个,可同时带
     * invitees没有受邀者带空数组或不带此属性
     *
     * @param callback
     */


    meetingExt.schedule = function (data, callback) {
      meeting.schedule(data, callback);
    };
    /**
     * 加入会议接口
     * @param data {meetingNum:'会议号， string 必填', password:'会议密码，int, 选填'}
     */


    meetingExt.join = function (data, callback) {
      meeting.join(data, callback);
    };

    var message = {};
    /**
     * 发送聊天消息接口(单聊与群聊)(文本消息)
     * @param data {sessionId:"会话id"(int类型)，msgBody:"聊天消息内容",atList:"群聊消息中指定@的成员账号"}
     *
     * 示例：{sessionId:100120023016,msgBody:"test1", atList:["92","93","all"]}(atList:是通讯录中的userId)
     *@param callback function
     */

    message.sendChatMsg = function (data, callback) {
      if (typeof callback !== "function") {
        console.error('sendChatMsg callback not function');
        return;
      }

      var pluginInfo = electronEvent.getPluginInfo();

      if (!pluginInfo.pluginId) {
        callback({
          errorCode: restCode.errorCode.FAIL
        });
        return;
      }

      if (!data) {
        callback({
          errorCode: restCode.errorCode.PARAM_EMPTY,
          errorInfo: restCode.errorMsg.PARAM_EMPTY
        });
        return false;
      }

      var messageParam = {
        requestId: new Date().getTime(),
        sessionId: data.sessionId,
        msgBody: data.msgBody,
        atList: data.atList
      };
      var request = {
        messageParam: messageParam,
        requestId: messageParam.requestId,
        callback: callback
      };
      pluginRequestCallback.push(request);
      electronEvent.postMsgToWave(action.sendMsg, messageParam);
    };

    var session = {};
    /**
     * 创建会话
     * sessionType: 1/2,1表示单聊，2表示群聊,
     * @param data {"sessionType":"session类型(int，必填)","groupName":“群组名(string,选填, 80)",memberList:"需要添加的成员列表(int数组，必填)"}
     * @param callback
     * memberList样例：memberList: [8002, 8003]
     * memberList可不带自己
     */

    session.createSession = function (data, callback) {
      if (typeof callback !== "function") {
        console.error('createSession callback not function');
        return;
      }

      var pluginInfo = electronEvent.getPluginInfo();

      if (!pluginInfo.pluginId) {
        callback({
          errorCode: restCode.errorCode.FAIL
        });
        return;
      }

      if (!data) {
        callback({
          errorCode: restCode.errorCode.PARAM_EMPTY,
          errorInfo: restCode.errorMsg.PARAM_EMPTY
        });
        return false;
      }

      var sessionParam = {
        requestId: new Date().getTime(),
        sessionType: data.sessionType,
        memberList: data.memberList,
        name: data.groupName
      };
      var request = {
        sessionParam: sessionParam,
        requestId: sessionParam.requestId,
        callback: callback
      };
      pluginRequestCallback.push(request);
      electronEvent.postMsgToWave(action.createSession, sessionParam);
    };

    var im = {};
    /**
     * 设置附件信息
     * @param data {url: '文件url'}
     * @param callback
     */

    im.setChatFileAttach = function (data, callback) {
      if (typeof callback !== "function") {
        console.error('setChatFileAttach callback not function');
        return;
      }

      var pluginInfo = electronEvent.getPluginInfo();

      if (!pluginInfo.pluginId) {
        callback({
          errorCode: restCode.errorCode.FAIL
        });
        return;
      }

      if (!data || !data.url) {
        callback({
          errorCode: restCode.errorCode.PARAM_EMPTY,
          errorInfo: restCode.errorMsg.PARAM_EMPTY
        });
        return;
      }

      var chatAttachParam = {
        requestId: new Date().getTime(),
        url: data.url,
        sessionId: pluginInfo.sessionId
      }; // Object.assign(chatAttachParam, data);

      var request = {
        chatAttachParam: chatAttachParam,
        requestId: chatAttachParam.requestId,
        callback: callback
      };
      pluginRequestCallback.push(request);
      electronEvent.postMsgToWave(action.setChatFileAttach, chatAttachParam);
    };

    var chatExt = {};
    /**
     * 创建会话
     * sessionType: 1/2,1表示单聊，2表示群聊,
     * @param data {
     * sessionType:"session类型(int，必填)",
     * groupName:“群组名(string,选填, 80)",
     * memberList:"需要添加的成员userId列表(int数组，必填最多500人（含自己）)"
     * }
     *
     * memberList样例：memberList: [8002, 8003]
     * memberList可不带自己
     *
     * @param callback {errorCode: '错误码',data:'session对象'}
     * 示例：{"errorCode":0,"errorMsg":"Operation success","data":{"sessionId":7036,"sessionType":1,"groupName":"","userIDBigger":6088,"userIDSmaller":6088,"userNameBigger":"dlliu-1145 -测试测试","userNameSmaller":"dlliu-1145 -测试测试"}}
     * session对象:
     *sessionId：int 会话id
     *sessionType: int 会话类型 1表示单聊，2表示群聊
     * groupName: string 群名
     *userIDBigger:单聊中user_id数字较大的一方
     * userIDSmaller:单聊中user_id数字较小的一方
     * userNameBigger:单聊中user_id数字较大一方的名称
     * userNameSmaller:单聊中user_id数字较小一方的名称
     */

    chatExt.createSession = function (data, callback) {
      session.createSession(data, function (result) {
        if (result) {
          if (result.errorCode !== restCode.errorCode.SUCCESS || !result.data) {
            callback(result);
          } else {
            var _session = {
              sessionId: result.data.sessionId,
              sessionType: result.data.sessionType,
              groupName: result.data.groupName,
              userIDBigger: result.data.userIDBigger,
              userIDSmaller: result.data.userIDSmaller,
              userNameBigger: result.data.userNameBigger,
              userNameSmaller: result.data.userNameSmaller
            };
            callback({
              errorCode: restCode.errorCode.SUCCESS,
              errorMsg: restCode.errorMsg.SUCCESS,
              data: _session
            });
          }
        } else {
          callback({
            errorCode: restCode.errorCode.FAIL,
            errorMsg: restCode.errorMsg.FAIL
          });
        }
      });
    };
    /**
     * 发送聊天消息接口(单聊与群聊)(文本消息)
     * @param data {
     * sessionId:"会话id,int类型, 必填"，
     * msgBody:"聊天消息内容, string, 最多5000,必填"
     * }
     * 示例：{sessionId:100120023016,msgBody:"test1"}
     *@param callback {errorCode: '错误码',data:'Message对象'}
     * 示例：{"errorCode":0,"errorMsg":"Operation success","data":{"msgId":76279,"time":1653027946832,"msgSeq":3,"msgType":1,"relMsgSeq":0,"relMsgInfo":"","msgSubType":0,"from":"6088","name":"dlliu-1145 -测试测试","msgBody":"2111111","sessionId":12430,"relSessionId":0,"fromName":"dlliu-1145-测试测试","avatarName":"dlliu-1145 -测试测试","tid":1653027946405}}
     * Message对象:
     * {
     * "msgId":76279,  int 消息id
     * "time":1653027946832,  int 消息时间戳(unix毫秒)
     * "msgSeq":3,  int 消息序列号
     * "msgType":1,  int 消息类型 1表示普通文本消息，2表示文件，3表示图片，4表示系统通知，5表示合并转发
     * "relMsgSeq":0,  int 关联的原始消息序列号
     * "relMsgInfo":"",  string 关联消息的内容
     * "msgSubType":0,  int 系统通知的具体类型：1表示有新用户用户进群，2表示有用户离开群，3表示解散群，4表示更改群名，5表示成员被踢出群聊，6表示群主转移，7表示消息撤回
     * "from":"6088",  int 消息发送人的user_id
     * "name":"dlliu-1145 -测试测试",  string 消息发送人的名字
     * "msgBody":"2111111", string 消息内容
     * "sessionId":12430,   int 会话id
     * "relSessionId":0,  int 关联会话的id
     * "fromName":"dlliu-1145-测试测试",  string 消息发送人的名字(最新)
     * "avatarName":"dlliu-1145 -测试测试",  string 用于生成头像的名字
     * "tid":1653027946405  int 会话ID
     * }
     *
     */


    chatExt.sendMessage = function (data, callback) {
      message.sendChatMsg(data, callback);
    };
    /**
     * 设置远端附件信息
     * @param data {url: '文件url'}
     * @param callback
     */


    chatExt.setChatFileAttach = function (data, callback) {
      im.setChatFileAttach(data, callback);
    };

    // 7.2.8 IsRegExp(argument)


    var MATCH = _wks('match');
    var _isRegexp = function (it) {
      var isRegExp;
      return _isObject(it) && ((isRegExp = it[MATCH]) !== undefined ? !!isRegExp : _cof(it) == 'RegExp');
    };

    // 7.3.20 SpeciesConstructor(O, defaultConstructor)


    var SPECIES$2 = _wks('species');
    var _speciesConstructor = function (O, D) {
      var C = _anObject(O).constructor;
      var S;
      return C === undefined || (S = _anObject(C)[SPECIES$2]) == undefined ? D : _aFunction(S);
    };

    // true  -> String#at
    // false -> String#codePointAt
    var _stringAt = function (TO_STRING) {
      return function (that, pos) {
        var s = String(_defined(that));
        var i = _toInteger(pos);
        var l = s.length;
        var a, b;
        if (i < 0 || i >= l) return TO_STRING ? '' : undefined;
        a = s.charCodeAt(i);
        return a < 0xd800 || a > 0xdbff || i + 1 === l || (b = s.charCodeAt(i + 1)) < 0xdc00 || b > 0xdfff
          ? TO_STRING ? s.charAt(i) : a
          : TO_STRING ? s.slice(i, i + 2) : (a - 0xd800 << 10) + (b - 0xdc00) + 0x10000;
      };
    };

    var at = _stringAt(true);

     // `AdvanceStringIndex` abstract operation
    // https://tc39.github.io/ecma262/#sec-advancestringindex
    var _advanceStringIndex = function (S, index, unicode) {
      return index + (unicode ? at(S, index).length : 1);
    };

    var $min = Math.min;
    var $push = [].push;
    var $SPLIT = 'split';
    var LENGTH = 'length';
    var LAST_INDEX$1 = 'lastIndex';
    var MAX_UINT32 = 0xffffffff;

    // babel-minify transpiles RegExp('x', 'y') -> /x/y and it causes SyntaxError
    var SUPPORTS_Y = !_fails(function () { RegExp(MAX_UINT32, 'y'); });

    // @@split logic
    _fixReWks('split', 2, function (defined, SPLIT, $split, maybeCallNative) {
      var internalSplit;
      if (
        'abbc'[$SPLIT](/(b)*/)[1] == 'c' ||
        'test'[$SPLIT](/(?:)/, -1)[LENGTH] != 4 ||
        'ab'[$SPLIT](/(?:ab)*/)[LENGTH] != 2 ||
        '.'[$SPLIT](/(.?)(.?)/)[LENGTH] != 4 ||
        '.'[$SPLIT](/()()/)[LENGTH] > 1 ||
        ''[$SPLIT](/.?/)[LENGTH]
      ) {
        // based on es5-shim implementation, need to rework it
        internalSplit = function (separator, limit) {
          var string = String(this);
          if (separator === undefined && limit === 0) return [];
          // If `separator` is not a regex, use native split
          if (!_isRegexp(separator)) return $split.call(string, separator, limit);
          var output = [];
          var flags = (separator.ignoreCase ? 'i' : '') +
                      (separator.multiline ? 'm' : '') +
                      (separator.unicode ? 'u' : '') +
                      (separator.sticky ? 'y' : '');
          var lastLastIndex = 0;
          var splitLimit = limit === undefined ? MAX_UINT32 : limit >>> 0;
          // Make `global` and avoid `lastIndex` issues by working with a copy
          var separatorCopy = new RegExp(separator.source, flags + 'g');
          var match, lastIndex, lastLength;
          while (match = _regexpExec.call(separatorCopy, string)) {
            lastIndex = separatorCopy[LAST_INDEX$1];
            if (lastIndex > lastLastIndex) {
              output.push(string.slice(lastLastIndex, match.index));
              if (match[LENGTH] > 1 && match.index < string[LENGTH]) $push.apply(output, match.slice(1));
              lastLength = match[0][LENGTH];
              lastLastIndex = lastIndex;
              if (output[LENGTH] >= splitLimit) break;
            }
            if (separatorCopy[LAST_INDEX$1] === match.index) separatorCopy[LAST_INDEX$1]++; // Avoid an infinite loop
          }
          if (lastLastIndex === string[LENGTH]) {
            if (lastLength || !separatorCopy.test('')) output.push('');
          } else output.push(string.slice(lastLastIndex));
          return output[LENGTH] > splitLimit ? output.slice(0, splitLimit) : output;
        };
      // Chakra, V8
      } else if ('0'[$SPLIT](undefined, 0)[LENGTH]) {
        internalSplit = function (separator, limit) {
          return separator === undefined && limit === 0 ? [] : $split.call(this, separator, limit);
        };
      } else {
        internalSplit = $split;
      }

      return [
        // `String.prototype.split` method
        // https://tc39.github.io/ecma262/#sec-string.prototype.split
        function split(separator, limit) {
          var O = defined(this);
          var splitter = separator == undefined ? undefined : separator[SPLIT];
          return splitter !== undefined
            ? splitter.call(separator, O, limit)
            : internalSplit.call(String(O), separator, limit);
        },
        // `RegExp.prototype[@@split]` method
        // https://tc39.github.io/ecma262/#sec-regexp.prototype-@@split
        //
        // NOTE: This cannot be properly polyfilled in engines that don't support
        // the 'y' flag.
        function (regexp, limit) {
          var res = maybeCallNative(internalSplit, regexp, this, limit, internalSplit !== $split);
          if (res.done) return res.value;

          var rx = _anObject(regexp);
          var S = String(this);
          var C = _speciesConstructor(rx, RegExp);

          var unicodeMatching = rx.unicode;
          var flags = (rx.ignoreCase ? 'i' : '') +
                      (rx.multiline ? 'm' : '') +
                      (rx.unicode ? 'u' : '') +
                      (SUPPORTS_Y ? 'y' : 'g');

          // ^(? + rx + ) is needed, in combination with some S slicing, to
          // simulate the 'y' flag.
          var splitter = new C(SUPPORTS_Y ? rx : '^(?:' + rx.source + ')', flags);
          var lim = limit === undefined ? MAX_UINT32 : limit >>> 0;
          if (lim === 0) return [];
          if (S.length === 0) return _regexpExecAbstract(splitter, S) === null ? [S] : [];
          var p = 0;
          var q = 0;
          var A = [];
          while (q < S.length) {
            splitter.lastIndex = SUPPORTS_Y ? q : 0;
            var z = _regexpExecAbstract(splitter, SUPPORTS_Y ? S : S.slice(q));
            var e;
            if (
              z === null ||
              (e = $min(_toLength(splitter.lastIndex + (SUPPORTS_Y ? 0 : q)), S.length)) === p
            ) {
              q = _advanceStringIndex(S, q, unicodeMatching);
            } else {
              A.push(S.slice(p, q));
              if (A.length === lim) return A;
              for (var i = 1; i <= z.length - 1; i++) {
                A.push(z[i]);
                if (A.length === lim) return A;
              }
              q = p = e;
            }
          }
          A.push(S.slice(p));
          return A;
        }
      ];
    });

    function compareVersion(version1, version2) {
      var version1Arr = version1.split('.');
      var version2Arr = version2.split('.');
      var maxL = Math.max(version1Arr.length, version2Arr.length);
      var result = 0;

      for (var i = 0; i < maxL; i++) {
        var preValue = version1Arr.length > i ? version1Arr[i] : 0;
        var preNum = isNaN(Number(preValue)) ? 0 : Number(preValue);
        var lastValue = version2Arr.length > i ? version2Arr[i] : 0;
        var lastNum = isNaN(Number(lastValue)) ? 0 : Number(lastValue);

        if (preNum < lastNum) {
          result = -1;
          break;
        } else if (preNum > lastNum) {
          result = 1;
          break;
        }
      }

      return result;
    }

    var commonService = {};
    /**
     * 获取终端版本号
     * @param callback
     */

    commonService.getCommonInfo = function (callback) {
      var currentInfo = {};
      var desktopVersion = common.getWaveDesktopVersion() || electronEvent.getPluginInfo().desktopVersion;
      var isWaveSupportPlugin = common.getIsWaveSupportPlugin();

      if (isWaveSupportPlugin === undefined) {
        isWaveSupportPlugin = electronEvent.getPluginInfo().isWaveSupportPlugin;
      }

      if (isWaveSupportPlugin) {
        var minSDKVersion = common.getMinSDKVersion() || electronEvent.getPluginInfo().minSDKVersion;
        var maxSDKVersion = common.getMaxSDKVersion() || electronEvent.getPluginInfo().maxSDKVersion;

        if (minSDKVersion && maxSDKVersion) {
          if (compareVersion(minSDKVersion, currentSDKVersion) !== 1 && compareVersion(maxSDKVersion, currentSDKVersion) !== -1) {
            isWaveSupportPlugin = 1;
          } else {
            isWaveSupportPlugin = 0;
          }
        }
      }

      if (desktopVersion) {
        currentInfo.waveVersion = desktopVersion;
        currentInfo.currentSDKVersion = currentSDKVersion;
        currentInfo.isWaveSupportPlugin = isWaveSupportPlugin;
        callback({
          errorCode: restCode.errorCode.SUCCESS,
          data: currentInfo
        });
      } else {
        callback({
          errorCode: restCode.errorCode.FAIL,
          errorInfo: restCode.errorMsg.FAIL
        });
      }
    };
    /**
     * 插件拦截器
     * @param data {interceptField:'需要拦截的url或url上的某些字符', hash:'拦截后跳转至插件的路由',
     * search:'跳转后url上参数',
     * origin:'跳转后url的origin, 默认跳插件的index.html页面'}
     */


    commonService.setPluginURLInterceptor = function (data) {
      if (!data || !data.interceptField || !data.hash) {
        console.error('plugin signature empty');
        return;
      }

      var interceptorInfo = {
        interceptField: data.interceptField,
        hash: data.hash,
        search: data.search,
        origin: data.origin
      };
      electronEvent.postMsgToWave(action.setPluginURLInterceptor, interceptorInfo);
    };
    /**
     * 清除缓存
     * @param data {origin:'需要清除cookie的域， string， 格式：scheme://host:port'}
     * @param callback
     */


    commonService.clearCookie = function (data, callback) {
      if (!data || !data.origin) {
        callback({
          errorCode: restCode.errorCode.PARAM_ERROR,
          errorMsg: restCode.errorMsg.PARAM_ERROR
        });
        return;
      }

      var cookieOption = {
        origin: data.origin,
        requestId: new Date().getTime()
      };

      electronEvent.postMsgToWave(action.clearCookie, cookieOption);
      callback({
        errorCode: restCode.errorCode.SUCCESS,
        errorMsg: restCode.errorMsg.SUCCESS
      });
    };

    var contact = {};
    /**
     * 获取联系人
     * @param callback
     */

    contact.getContactList = function (callback) {
      if (typeof callback !== "function") {
        console.error('getContactList callback not function');
        return;
      }

      var messageParam = {
        requestId: new Date().getTime()
      };
      var request = {
        messageParam: messageParam,
        requestId: messageParam.requestId,
        callback: callback
      };
      pluginRequestCallback.push(request);
      electronEvent.postMsgToWave(action.getContactList, messageParam);
    };

    var contactExt = {};
    /**
     * 获取联系人列表
     * @param callback {errorCode: '错误码', data:'[], 通讯录对象数组'}
     * {errorCode: 0, errorMsg: "Operation success", data: [{user}]}
     * user字段：
     * area: "kmye_test"  string 开启cloudIM时中配置的区域，未开启时为空
     * avatarName: "1000"   string 生成头像分机
     * comment: ""    string 备注
     * deptId: 628   int 所属部门ID
     * deviceId: 5   int 所属设备ID
     * dialExtension: "12343211000"   string 拨号分机
     * dialPrefix: "1234321"   string 外部呼入的前缀
     * displayExtension: "(1234321)1000"  string 显示分机
     * displayInDpt:   int 是否显示在部门层级中 0/1, 0:隐藏，1：显示
     * email:   string 邮箱
     * enableContact:   int 是否显示在通讯录列表 0:不显示，1：显示
     * enableWave:   int 是否使能wave 0:不使能 1：使能
     * extension:   string 分机号与userName一致
     * familyNumber:  string  家庭号码
     * favor:   int 是否被收藏，0/1 0：否 1：是 默认为0
     * fax:   string 传真
     * firstName:  string 第一个名字
     * fullName:  string 全名
     * icon:   int 是否设置了自定义头像， 0/1, 0:没有,1:有
     * iconTimestamp:   int 最后一次修改或重置头像的时间戳
     * lastName:  string  后一个名字
     * phoneNumber:  string 手机号码
     * status: string  状态：Idle（空闲），InUse（忙碌），Unavailable(脱机)，Dnd（勿扰），Away（离开）
     * title:    string 职位
     * userId:  int User对应的ID
     * userName:  string 分机号
     * userType:  int 联系人类型，0/1,0:普通联系人，1:外部联系人
     * workStatus:  string 工作状态,目前有7种状态：、无（0）、正在会议（1）、正在出差（2）、远程办公（3）、生病请假（4）、正在休假（5）、自定义状态（6），默认为0
     * workStatusBody:  string 工作状态为自定义时的内容
     */

    contactExt.getContactList = function (callback) {
      contact.getContactList(callback);
    };

    /*
    * 暴露给上层的接口
    */
    var pluginSDK = {};
    pluginSDK.call = callExt;
    pluginSDK.log = logExt;
    pluginSDK.userConfig = userConfigExt;
    pluginSDK.meeting = meetingExt;
    pluginSDK.chat = chatExt;
    pluginSDK.contact = contactExt; //Enum

    pluginSDK.MsgType = MsgType;
    pluginSDK.MsgSubType = MsgSubType;
    pluginSDK.SessionType = SessionType;
    pluginSDK.StatuType = ExtensionStatus;
    pluginSDK.WorkStatusType = WorkStatus;
    pluginSDK.CycleType = MeetingCycleType;
    pluginSDK.ErrorCode = restCode.errorCode;
    pluginSDK.EventType = pluginEvent;
    /**
     * 隐藏窗口
     */

    pluginSDK.hideWindow = function () {
      pluginWin.hideWindow();
    };
    /**
     * 关闭窗口
     */


    pluginSDK.closeWindow = function () {
      pluginWin.closeWindow();
    };
    /**
     * 使用默认窗口并显示
     * @param data {width:'宽度(int)',height:'高度(int)',
     * winX:'窗口相对于屏幕左侧的偏移量(如果使用了Y,此必选)(int)',winY:'窗口相对于屏幕顶端的偏移量(如果使用了X,此必选)(int)',
     * center:'是否居中true/false（与X,Y互斥）', show:'是否显示true/fase'}
     */


    pluginSDK.setDefaultWindow = function (data) {
      pluginWin.setDefaultWindow(data);
    };
    /**
     * 复用wave通知窗口并显示
     * @param data {notificationBody:'通知消息内容体(html节点)'}
     */


    pluginSDK.displayNotification = function (data) {
      pluginWin.showNotificationWindow(data);
    };
    /**
     * 隐藏插件通知窗口
     * @param data
     */


    pluginSDK.hideNotification = function () {
      pluginWin.hideNotificationWindow();
    };
    /**
     * 设置插件签名
     * @param data {signature:'签名字符串'}
     */


    pluginSDK.setPluginSignature = function (data) {
      userConfigExt.setPluginSignature(data);
    };
    /**
     * 事件绑定接口
     * imSDK.eventEmitter.on(eventName, handle)
     * 事件触发接口
     * imSDK.eventEmitter.trigger(eventName, data)
     * 事件解绑接口
     * imSDK.eventEmitter.off(eventName)
     * @param eventName: onError, recvMessage
     *   handle: callback function
     *   data: 传递给handle的数据
     * @param method: on, trigger, off, once
     *   绑定: imSDK.eventEmitter.on("onError", (obj) => {})
     *   触发: imSDK.eventEmitter.trigger("onError", obj),
     *   解绑: imSDK.eventEmitter.off("onError")
     */


    pluginSDK.eventEmitter = bindEvent;
    /**
     * 获取通用信息包含：wave终端版本号，当前SDK版本号等
     * @param callback
     */

    pluginSDK.getCommonInfo = function (callback) {
      commonService.getCommonInfo(callback);
    };
    /**
     * 插件拦截器
     * @param data {interceptField:'需要拦截的url或url上的某些字符',
     * hash:'拦截后跳转至插件的路由', search:'跳转后url上参数',
     * origin:'跳转后url的origin, 默认跳插件的index.html页面'}
     */


    pluginSDK.setPluginURLInterceptor = function (data) {
      commonService.setPluginURLInterceptor(data);
    };
    /**
     * 清除cookie
     * @param data {origin:'需要清除cookie的域， string， 格式：scheme://host:port'}
     * @param callback
     */


    pluginSDK.clearCookie = function (data, callback) {
      commonService.clearCookie(data, callback);
    };

    return pluginSDK;

})));
