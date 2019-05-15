"""
Parameter views provide ways to read and write parameter data with a defined unit
and time information.
"""

import numbers
from typing import Any, Optional, Sequence, Tuple, cast

import numpy as np
from numpy.lib.mixins import NDArrayOperatorsMixin
from pandas.core.arrays.base import ExtensionOpsMixin

from ..errors import ParameterEmptyError, TimeseriesPointsValuesMismatchError
from .parameters import ParameterType, _Parameter
from .time import ExtrapolationType, InterpolationType, TimeseriesConverter
from .units import UnitConverter

# pylint: disable=protected-access


class _Timeseries(ExtensionOpsMixin, NDArrayOperatorsMixin):  # type: ignore
    __array_priority__ = 1000
    _HANDLED_TYPES = (np.ndarray, numbers.Number)
    _ndarray: np.ndarray

    def __init__(self, input_array, parameter_view):
        self._ndarray = np.asarray(input_array)
        self._parameter_view = parameter_view

    def __read__(self):
        self._parameter_view._read()
        return self

    def __write__(self):
        self._parameter_view._write()
        return self

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs):
        args = [
            i.__read__()._ndarray if isinstance(i, type(self)) else i for i in inputs
        ]
        outputs = kwargs.pop("out", None)
        if outputs:
            kwargs["out"] = tuple(
                i._ndarray if isinstance(i, type(self)) else i for i in outputs
            )
            results = self._ndarray.__array_ufunc__(ufunc, method, *args, **kwargs)
            if results is NotImplemented:
                return NotImplemented
            if ufunc.nout == 1:
                results = (results,)
            results = tuple(
                (output.__write__() if isinstance(output, type(self)) else result)
                for result, output in zip(results, outputs)
            )
            return results[0] if len(results) == 1 else results
        return self._ndarray.__array_ufunc__(ufunc, method, *args, **kwargs)

    def __getitem__(self, item):
        self.__read__()
        result = self._ndarray[item]
        if not isinstance(item, int):
            result = type(self)(result, self._parameter_view)
        return result

    def __setitem__(self, key, val):
        self._ndarray[key] = val
        self.__write__()

    def __iter__(self):
        self.__read__()
        for i in self._ndarray:
            yield i

    def __repr__(self):
        return "timeseries({})".format(repr(self._ndarray))

    def __array__(self, dtype=None):
        return np.asarray(self._ndarray, dtype=dtype)

    def __len__(self):
        return len(self._ndarray)

    @property
    def dtype(self):
        return self._ndarray.dtype

    @property
    def ndim(self):
        return 1

    @property
    def nbytes(self):
        self.__read__()
        return self._ndarray.nbytes

    @property
    def shape(self) -> Tuple[int, ...]:
        return cast(Tuple[int, ...], self._ndarray.shape)

    @classmethod
    def _create_arithmetic_method(cls, op):
        def arithmetic_method(self, other):
            if isinstance(other, cls):
                other = other._ndarray

            with np.errstate(all="ignore"):
                return op(self._ndarray, other)

        arithmetic_method.__name__ = "__{}__".format(op.__name__)
        arithmetic_method.__qualname__ = "{cl}.__{name}__".format(
            cl=cls.__name__, name=op.__name__
        )
        arithmetic_method.__module__ = cls.__module__
        return arithmetic_method

    _create_comparison_method = _create_arithmetic_method


_Timeseries._add_arithmetic_ops()
_Timeseries._add_comparison_ops()


class ParameterView:
    """
    Generic view to a :ref:`parameter <parameters>` (scalar or timeseries).
    """

    _parameter: _Parameter
    """Parameter"""

    def __init__(self, parameter: _Parameter):
        """
        Initialize.

        Parameters
        ----------
        parameter
            Parameter
        """
        self._parameter = parameter

    @property
    def empty(self) -> bool:
        """
        Check if parameter is empty, i.e. has not yet been written to.
        """
        return not self._parameter.has_been_written_to


class ScalarView(ParameterView):
    """
    Read-only view of a scalar parameter.
    """

    _child_data_views: Sequence["ScalarView"]
    """List of views to the child parameters for aggregated reads"""

    _unit_converter: UnitConverter
    """Unit converter"""

    def __init__(self, parameter: _Parameter, unit: str):
        """
        Initialize.

        Parameters
        ----------
        parameter
            Parameter
        unit
            Unit for the values in the view
        """
        super().__init__(parameter)
        self._unit_converter = UnitConverter(cast(str, parameter.info.unit), unit)

        def get_data_views_for_children_or_parameter(
            parameter: _Parameter
        ) -> Sequence["ScalarView"]:
            if parameter.children:
                return sum(
                    (
                        get_data_views_for_children_or_parameter(p)
                        for p in parameter.children.values()
                    ),
                    [],
                )
            return [ScalarView(parameter, self._unit_converter.target)]

        if self._parameter.children:
            self._child_data_views = get_data_views_for_children_or_parameter(
                self._parameter
            )

    @property
    def value(self) -> float:
        """
        Get current value of scalar parameter.

        If the parameter has child parameters (i.e. ``_children`` is not empty),
        the returned value will be the sum of the values of all of the child
        parameters.

        Returns
        -------
        float
            Current value of parameter

        Raises
        ------
        ParameterEmptyError
            Parameter is empty, i.e. has not yet been written to
        """
        if self._parameter.children:
            return sum(v.value for v in self._child_data_views)
        if self.empty:
            raise ParameterEmptyError

        return self._unit_converter.convert_from(cast(float, self._parameter.data))


class WritableScalarView(ScalarView):
    """
    View of a scalar parameter whose value can be changed.
    """

    @property
    def value(self) -> float:
        """
        Get current value of scalar parameter.

        If the parameter has child parameters (i.e. ``_children`` is not empty),
        the returned value will be the sum of the values of all of the child
        parameters.

        Returns
        -------
        float
            Current value of parameter

        Raises
        ------
        ParameterEmptyError
            Parameter is empty, i.e. has not yet been written to
        """
        return super().value

    @value.setter
    def value(self, v: float) -> None:
        """
        Set current value of scalar parameter.

        Parameters
        ----------
        v
            Value
        """
        self._parameter.data = self._unit_converter.convert_to(v)


class TimeseriesView(ParameterView):
    """
    Read-only :class:`ParameterView` of a timeseries.
    """

    _child_data_views: Sequence["TimeseriesView"]
    """List of views to the child parameters for aggregated reads"""

    _timeseries: Optional[_Timeseries]
    _data: Optional[np.ndarray]
    _version: int

    _timeseries_converter: TimeseriesConverter
    """Timeseries converter"""

    _unit_converter: UnitConverter
    """Unit converter"""

    def __init__(
        self,
        parameter: _Parameter,
        unit: str,
        time_points: np.ndarray,
        timeseries_type: ParameterType,
        interpolation_type: InterpolationType,
        extrapolation_type: ExtrapolationType,
    ):
        """
        Initialize.

        Parameters
        ----------
        parameter
            Parameter
        unit
            Unit for the values in the view
        time_points
            Timeseries time points
        timeseries_type
            Time series type
        interpolation_type
            Interpolation type
        extrapolation_type
            Extrapolation type
        """
        super().__init__(parameter)
        self._unit_converter = UnitConverter(cast(str, parameter.info.unit), unit)
        self._timeseries_converter = TimeseriesConverter(
            parameter.time_points,
            time_points,
            timeseries_type,
            interpolation_type,
            extrapolation_type,
        )  # TimeseriesConverter
        self._data = None
        self._timeseries = None

        def get_data_views_for_children_or_parameter(
            parameter: _Parameter
        ) -> Sequence["TimeseriesView"]:
            if parameter.children:
                return sum(
                    (
                        get_data_views_for_children_or_parameter(p)
                        for p in parameter.children.values()
                    ),
                    [],
                )
            return [
                TimeseriesView(
                    parameter,
                    self._unit_converter.target,
                    self._timeseries_converter._target,  # pylint: disable=protected-access
                    timeseries_type,
                    interpolation_type,
                    extrapolation_type,
                )
            ]

        if self._parameter.children:
            self._child_data_views = get_data_views_for_children_or_parameter(
                self._parameter
            )

    def _read(self):
        if self._data is None:
            self._data = self._get_values()
        elif self._version != self._parameter.version:
            np.copyto(self._data, self._get_values())
        self._version = self._parameter.version

    def _write(self):
        raise NotImplementedError  # TODO

    def _get_values(self) -> np.ndarray:
        if self._parameter.children:
            return cast(
                Sequence[float], np.sum(v.values for v in self._child_data_views)
            )
        if self.empty:
            raise ParameterEmptyError

        return cast(
            Sequence[float],
            self._timeseries_converter.convert_from(
                self._unit_converter.convert_from(
                    cast(Sequence[float], self._parameter.data)
                )
            ),
        )

    @property
    def values(self) -> _Timeseries:
        """
        Get values of the full timeseries.

        If the parameter has child parameters (i.e. ``_children`` is not empty),
        the returned value will be the sum of the values of all of the child
        parameters.

        Returns
        -------
        Sequence[float]
            Current value of parameter

        Raises
        ------
        ParameterEmptyError
            Parameter is empty, i.e. has not yet been written to
        """
        if self._timeseries is None:
            self._read()
            self._timeseries = _Timeseries(self._data, self)
        return self._timeseries

    @property
    def length(self) -> int:
        """
        Length of timeseries.
        """
        return self._timeseries_converter.target_length


class WritableTimeseriesView(TimeseriesView):
    """
    View of a timeseries whose values can be changed.
    """

    def _write(self):
        self._parameter.data = self._timeseries_converter.convert_to(
            self._unit_converter.convert_to(self._data)
        )
        self._parameter.version += 1
        self._version = self._parameter.version

    @property
    def values(self) -> _Timeseries:  # TODO Docs
        """
        Get values of the full timeseries.

        If the parameter has child parameters (i.e. ``_children`` is not empty),
        the returned value will be the sum of the values of all of the child
        parameters.

        Returns
        -------
        Sequence[float]
            Current value of parameter

        Raises
        ------
        ParameterEmptyError
            Parameter is empty, i.e. has not yet been written to
        """
        return super().values

    @values.setter
    def values(self, v: Sequence[float]) -> None:
        """
        Set value for whole time series.

        Parameters
        ----------
        v
            Values to set

        Raises
        ------
        TimeseriesPointsValuesMismatchError
            Lengths of ``v`` and the time points number mismatch
        """
        if len(v) != self._timeseries_converter.target_length:
            raise TimeseriesPointsValuesMismatchError
        if self._data is None:
            self._data = np.asarray(v).copy()
            self._timeseries = _Timeseries(self._data, self)
        else:
            np.copyto(self._data, np.asarray(v))
        self._write()


class GenericView(ParameterView):
    """
    Read-only view of a generic parameter.
    """

    @property
    def value(self) -> Any:
        """
        Get current value of generic parameter.

        Returns
        -------
        Any
            Current value of parameter

        Raises
        ------
        ParameterEmptyError
            Parameter is empty, i.e. has not yet been written to
        """
        if self.empty:
            raise ParameterEmptyError

        return self._parameter.data


class WritableGenericView(GenericView):
    """
    View of a generic parameter whose value can be changed.
    """

    @property
    def value(self) -> Any:
        """
        Get current value of generic parameter.

        Returns
        -------
        Any
            Current value of parameter

        Raises
        ------
        ParameterEmptyError
            Parameter is empty, i.e. has not yet been written to
        """
        return super().value

    @value.setter
    def value(self, v: Any) -> None:
        """
        Set current value of boolean parameter.

        Parameters
        ----------
        v
            Value
        """
        self._parameter.data = v