from typing import Any, Dict, Tuple, List, Type
from typing_inspect import is_optional_type
from dataclasses import fields, is_dataclass

from .core import SerdeError, FROM_DICT, FROM_TUPLE, T, gen, iter_types


def from_any(cls, o):
    if not is_deserializable(cls):
        raise SerdeError('`cls` must be deserializable.')

    if isinstance(o, (List, Tuple)):
        return cls.__serde_from_tuple__(o)
    elif isinstance(o, Dict):
        return cls.__serde_from_dict__(o)
    elif isinstance(o, cls):
        return o
    else:
        raise SerdeError(f'`o` must be either List, Tuple, Dict or cls but {type(o)}.')


def from_tuple(cls) -> str:
    """
    Generate function to deserialize from tuple.
    """
    params = []
    for i, f in enumerate(fields(cls)):
        params.append(f'{f.name}=' + from_value(f.type, f'data[{i}]'))
    return ', '.join(params)


def from_dict(cls) -> str:
    """
    Generate function to deserialize from dict.
    """
    params = []
    for f in fields(cls):
        params.append(f'{f.name}=' + from_value(f.type, f'data["{f.name}"]'))
    return ', '.join(params)


def from_value(typ: Type, varname: str) -> str:
    """
    Generate function to deserialize from value.
    """
    # If a member is also pyserde class, invoke the own deserialize function
    if is_deserializable(typ):
        nested = f'{typ.__name__}'
        s = f"from_any({nested}, {varname})"
    elif is_optional_type(typ):
        s = varname
    elif issubclass(typ, List):
        element_typ = typ.__args__[0]
        s = f"[{from_value(element_typ, 'd')} for d in {varname}]"
    elif issubclass(typ, Dict):
        key_typ = typ.__args__[0]
        value_typ = typ.__args__[1]
        s = (f"{{ {from_value(key_typ, 'k')}: {from_value(value_typ, 'v')} "
             f"for k, v in {varname}.items() }}")
    elif issubclass(typ, Tuple):
        elements = [from_value(arg, varname + f'[{i}]') + ', ' for i, arg in enumerate(typ.__args__)]
        s = f"({''.join(elements)})"
    else:
        s = varname
    return s


def gen_from_function(cls: Type[T], funcname: str, params: str) -> Type[T]:
    """
    Generate function to deserialize from tuple.
    """
    body = (f'def {funcname}(data):\n return cls({params})')

    globals: Dict[str, Any] = dict(cls=cls)

    # Collect fields to be used in the scope of exec.
    for typ in iter_types(cls):
        if is_dataclass(typ):
            globals[typ.__name__] = typ
    globals['from_any'] = from_any

    gen(body, globals)
    setattr(cls, funcname, staticmethod(globals[funcname]))

    return cls


def is_deserializable(instance_or_class: Any) -> bool:
    """
    Test if `instance_or_class` is deserializable.
    """
    return hasattr(instance_or_class, FROM_TUPLE) or hasattr(instance_or_class, FROM_DICT)


class Deserializer:
    """
    Deserializer base class.
    """
    def deserialize(self, obj):
        return obj


def deserialize(_cls=None, rename_all: bool = False) -> Type:
    """
    `deserialize` decorator. A dataclass with this decorator can be
    deserialized into an object from various data interchange format
    such as JSON and MsgPack.
    """
    def wrap(cls) -> Type:
        cls = gen_from_function(cls, FROM_TUPLE, from_tuple(cls))
        cls = gen_from_function(cls, FROM_DICT, from_dict(cls))
        return cls

    if _cls is None:
        wrap

    return wrap(_cls)


def from_obj(c: Type[T], o: Any, de: Type[Deserializer] = None, **opts) -> T:
    if de:
        o = de().deserialize(o, **opts)
    if o is None:
        return None
    if is_deserializable(c):
        return from_any(c, o)
    elif is_optional_type(c):
        return from_obj(c.__args__[0], o)
    elif issubclass(c, List):
        return [from_obj(c.__args__[0], e) for e in o]
    elif issubclass(c, Tuple):
        return tuple(from_obj(c.__args__[i], e) for i, e in enumerate(o))
    elif issubclass(c, Dict):
        return {from_obj(c.__args__[0], k): from_obj(c.__args__[1], v) for k, v in o.items()}
    else:
        return o