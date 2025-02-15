import inspect
import typing
from typing import Callable, Any, Dict, Type, MutableMapping

from pydantic import BaseModel
from pydantic_core import core_schema


"""
class PolymorphicBaseModel(BaseModel):
    __polymorphic__ = False
    _subtypes: Dict[str, Type[BaseModel]] = dict()

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        __source: type["BaseModel"],
        __handler: Callable[[Any], core_schema.CoreSchema],
    ) -> core_schema.CoreSchema:
        schema = typing.cast(MutableMapping[str, Any], __handler(__source))
        og_schema_ref = schema["ref"]
        schema["ref"] += ":aux"

        return core_schema.no_info_before_validator_function(
            cls.__convert_to_real_type__, schema=schema, ref=og_schema_ref
        )

    @classmethod
    def __convert_to_real_type__(cls, value: Any):
        if not cls.__polymorphic__:
            return value

        if isinstance(value, dict) is False:
            return value

        value = value.copy()

        subclass = value.pop("type", None)
        if subclass is None:
            raise ValueError(f"Missing 'type' in {cls.__name__}")

        try:
            for dtype in cls.get_subclasses():
                if dtype.type == subclass:
                    return dtype(**value)
        except StopIteration as e:
            raise TypeError(f"Unsupported subclass: {subclass}") from e

    @classmethod
    def get_subclasses(cls):
        types = []
        for x in cls.__subclasses__():
            if not inspect.isabstract(x):
                types.append(x)
            else:
                types.extend(list(x.get_subclasses()))

        return tuple(types)

    def __init_subclass__(cls, polymorphic: bool = False, type=None, **kwargs):
        cls.__polymorphic__ = polymorphic
        super().__init_subclass__(**kwargs)
        if type:
            # n.b. if a subclass declares its own _subtypes dict, it'll take precedence over this one.
            # This would allow us to re-use the same type names across different classes.
            if type in cls._subtypes:
                raise AttributeError(
                    f"Class {cls} cannot be registered with polymorphic type='{type}' because it's already registered "
                    f" to {cls._subtypes[type]}"
                )
            cls._subtypes[type] = cls
"""
