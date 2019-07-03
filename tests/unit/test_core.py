import re
import warnings

import numpy as np
import pytest

from openscm import OpenSCM
from openscm.core.parameters import ParameterType
from openscm.core.parameterset import ParameterSet
from openscm.core.time import create_time_points
from openscm.errors import (
    DimensionalityError,
    ParameterAggregationError,
    ParameterEmptyError,
    ParameterReadError,
    ParameterReadonlyError,
    ParameterTypeError,
    ParameterWrittenError,
    RegionAggregatedError,
    TimeseriesPointsValuesMismatchError,
)


@pytest.fixture
def model_name():
    return "DICE"


@pytest.fixture
def start_time():
    return np.datetime64("2000-01-01")


@pytest.fixture
def stop_time():
    return np.datetime64("2010-01-01")


@pytest.fixture
def model(model_name):
    model = OpenSCM(model_name)
    model.parameters._get_or_create_region(("World", "DEU", "BER"))
    return model


@pytest.fixture
def model_run(model_name, start_time, stop_time):
    model_run = OpenSCM(model_name)
    model_run.parameters.generic("Start Time").value = start_time
    model_run.parameters.generic("Stop Time").value = stop_time
    YEAR = np.timedelta64(365, "D")
    npoints = int((stop_time - start_time) / YEAR) + 1  # include self._stop_time
    model_run.parameters.timeseries(
        ("Emissions", "CO2"),
        "GtCO2/a",
        create_time_points(
            start_time,
            stop_time - start_time,
            npoints,
            ParameterType.AVERAGE_TIMESERIES,
        ),
        timeseries_type="average",
    ).values = np.zeros(npoints)
    return model_run


def test_model_run(model_run, model_name):
    assert model_run.model == model_name
    model_run.run()
    assert model_run.output.info(("Pool", "CO2", "Atmosphere"))


def test_model_stepping(model_run, model_name):
    assert model_run.model == model_name
    model_run.reset_stepping()
    model_run.step()
    assert model_run.output.info(("Pool", "CO2", "Atmosphere"))


def test_region(model):
    parameterset = model.parameters

    with pytest.raises(ValueError, match="No region name given"):
        parameterset._get_or_create_region(())

    for accessor in ["World", ("World"), ("World",), ["World"]]:
        with warnings.catch_warnings():
            # silence warning about conversion, that's tested elsewhere
            warnings.simplefilter("ignore")
            region_world = parameterset._get_or_create_region(accessor)
        assert region_world.full_name == ("World",)
        assert region_world.name == "World"

    for accessor in [("World", "DEU"), ["World", "DEU"]]:
        region_deu = parameterset._get_or_create_region(accessor)
        assert region_deu.full_name == ("World", "DEU")
        assert region_deu.name == "DEU"

    region_ber = parameterset._get_or_create_region(("World", "DEU", "BER"))
    assert region_ber.full_name == ("World", "DEU", "BER")
    assert region_ber.name == "BER"
    assert region_ber.parent == region_deu

    region_deu.attempt_aggregate()
    with pytest.raises(RegionAggregatedError):
        parameterset._get_or_create_region(("World", "DEU", "BRB"))

    assert parameterset._get_region(("INVALID", "DEU", "BER")) is None


def test_parameter(model):
    parameterset = model.parameters
    region_ber = parameterset._get_or_create_region(("World", "DEU", "BER"))

    with pytest.raises(ValueError, match="No parameter name given"):
        parameterset._get_or_create_parameter((), region_ber)

    param_co2 = parameterset._get_or_create_parameter(("Emissions", "CO2"), region_ber)
    # not clear what the value of being able to access with `()` is...
    assert param_co2.get_subparameter(()) == param_co2
    for accessor in ["CO2", ("CO2"), ("CO2",), ["CO2"]]:
        assert param_co2.parent.get_subparameter(accessor) == param_co2
    assert region_ber.get_parameter(("Emissions", "CO2")) == param_co2
    assert param_co2.full_name == ("Emissions", "CO2")
    assert param_co2.region.full_name == ("World", "DEU", "BER")
    assert param_co2.name == "CO2"
    info = parameterset.info(("Emissions", "CO2"), ("World", "DEU", "BER"))
    assert info.name == param_co2.full_name
    assert info.region == param_co2.region.full_name
    for accessor in ["Emissions", ("Emissions"), ("Emissions",), ["Emissions"]]:
        info = parameterset.info(accessor, ("World", "DEU", "BER"))
        assert info.name == param_co2.parent.full_name
        assert info.region == param_co2.parent.region.full_name
    assert parameterset.info(("Emissions", "NOx"), ("World", "DEU", "BER")) is None
    assert parameterset.info(("Emissions",), ("World", "DEU", "BRB")) is None

    with pytest.raises(ValueError, match="No parameter name given"):
        parameterset.info(None, ("World", "DEU", "BER"))
    with pytest.raises(ValueError, match="No parameter name given"):
        parameterset.info((), ("World", "DEU", "BER"))

    param_emissions = param_co2.parent
    assert param_emissions.full_name == ("Emissions",)
    assert param_emissions.name == "Emissions"
    # Before any read/write attempt these should be None:
    assert param_emissions.parameter_type is None
    assert param_emissions.unit is None

    param_industry = parameterset._get_or_create_parameter(
        ("Emissions", "CO2", "Industry"), region_ber
    )
    assert param_industry.full_name == ("Emissions", "CO2", "Industry")
    assert param_industry.name == "Industry"

    param_industry.attempt_read(
        ParameterType.AVERAGE_TIMESERIES, "GtCO2/a", np.array([0])
    )
    assert param_industry.parameter_type == ParameterType.AVERAGE_TIMESERIES
    assert param_industry.unit == "GtCO2/a"

    with pytest.raises(ParameterReadonlyError):
        param_co2.attempt_write(
            ParameterType.AVERAGE_TIMESERIES, "GtCO2/a", np.array([0])
        )

    param_co2.attempt_read(ParameterType.AVERAGE_TIMESERIES, "GtCO2/a", np.array([0]))
    with pytest.raises(ParameterTypeError):
        param_co2.attempt_read(ParameterType.SCALAR, "GtCO2/a")

    with pytest.raises(ParameterReadError):
        parameterset._get_or_create_parameter(
            ("Emissions", "CO2", "Landuse"), region_ber
        )

    with pytest.raises(ParameterTypeError):
        param_industry.attempt_write(ParameterType.SCALAR, "GtCO2/a")

    param_industry.attempt_write(
        ParameterType.AVERAGE_TIMESERIES, "GtCO2/a", np.array([0])
    )
    with pytest.raises(ParameterWrittenError):
        parameterset._get_or_create_parameter(
            ("Emissions", "CO2", "Industry", "Other"), region_ber
        )


def test_parameterset_default_initialization():
    paraset = ParameterSet()

    assert paraset._get_or_create_region(("World",)) == paraset._root
    error_msg = (
        "Cannot access region Earth, root region for this parameter set is World"
    )
    with pytest.raises(ValueError, match=error_msg):
        paraset._get_or_create_region("Earth")


def test_parameterset_named_initialization():
    paraset_named = ParameterSet("Earth")
    assert paraset_named._get_or_create_region(("Earth",)) == paraset_named._root


def test_parameterset_get_region_str():
    paraset = ParameterSet()
    paraset._get_or_create_region("World|Test")
    r = paraset._get_region("World|Test")
    assert r.full_name == ("World", "Test")

    paraset._get_or_create_region("World|Second test|Lower")

    root = paraset._root
    r2 = root.get_subregion("Second test|Lower")
    assert r2.full_name == ("World", "Second test", "Lower")


@pytest.mark.parametrize("view_type", ["scalar", "timeseries", "generic"])
def test_view_str_rep(view_type):
    paraset = ParameterSet()
    para_name = "example"
    if view_type == "generic":
        unit = "undefined"
        v = paraset.generic(para_name)
        assert str(v) == "View of {} in {}".format(para_name, unit)
    elif view_type == "scalar":
        unit = "kg"
        v = paraset.scalar(para_name, unit)
        assert str(v) == "View of {} {} in {}".format(view_type, para_name, unit)
    elif view_type == "timeseries":
        unit = "kg"
        tp = create_time_points(
            np.datetime64("2010-01-01"), np.timedelta64(365, "D"), 10, "average"
        )
        v = paraset.timeseries(para_name, unit, tp)
        assert str(v) == "View of {} {} in {}".format(view_type, para_name, unit)


def test_version():
    paraset = ParameterSet()
    v1 = paraset.scalar("example", unit="g")
    v2 = paraset.scalar("example", unit="kg")

    assert v1.version == 0
    assert v2.version == 0

    v1.value = 3

    assert v1.version == 1
    assert v2.version == 1

    v2.value = 12

    assert v1.version == 2
    assert v2.version == 2


def test_ensure():
    paraset = ParameterSet()

    para = "example"
    unit = "g"
    v1 = paraset.scalar(para, unit=unit)

    error_msg = re.escape("Parameter {} in {} is required but empty".format(para, unit))
    with pytest.raises(ParameterEmptyError, match=error_msg):
        v1.ensure()

    v1.value = 3
    v1.ensure()


def test_scalar_parameter_view(model):
    parameterset = model.parameters
    cs = parameterset.scalar("Climate Sensitivity", "degC")
    with pytest.raises(ParameterEmptyError):
        cs.value
    assert cs.empty
    cs_writable = parameterset.scalar("Climate Sensitivity", "degF")
    cs_writable.value = 68
    assert cs_writable.value == 68
    assert not cs.empty
    np.testing.assert_allclose(cs.value, 20)
    with pytest.raises(ParameterTypeError):
        parameterset.timeseries("Climate Sensitivity", "degC", (0,))
    with pytest.raises(DimensionalityError):
        parameterset.scalar("Climate Sensitivity", "kg")
    cs_writable.value = 45
    assert cs_writable.value == 45


def test_scalar_parameter_view_aggregation(model):
    ta_1 = 0.6
    ta_2 = 0.3
    tb = 0.1

    parameterset = model.parameters

    a_1_writable = parameterset.scalar(("Top", "a", "1"), "dimensionless")
    a_1_writable.value = ta_1

    a_2_writable = parameterset.scalar(("Top", "a", "2"), "dimensionless")
    a_2_writable.value = ta_2

    b_writable = parameterset.scalar(("Top", "b"), "dimensionless")
    b_writable.value = tb

    a_1 = parameterset.scalar(("Top", "a", "1"), "dimensionless")
    np.testing.assert_allclose(a_1.value, ta_1)

    a_2 = parameterset.scalar(("Top", "a", "2"), "dimensionless")
    np.testing.assert_allclose(a_2.value, ta_2)

    a = parameterset.scalar(("Top", "a"), "dimensionless")
    np.testing.assert_allclose(a.value, ta_1 + ta_2)

    b = parameterset.scalar(("Top", "b"), "dimensionless")
    np.testing.assert_allclose(b.value, tb)

    with pytest.raises(ParameterReadonlyError):
        parameterset.scalar(("Top", "a"), "dimensionless").value = 0

    total = parameterset.scalar(("Top"), "dimensionless")
    np.testing.assert_allclose(total.value, ta_1 + ta_2 + tb)


@pytest.fixture(
    params=[
        (range(5 * 365), [0.24373829, 0.7325541, 1.22136991, 1.71018572, 2.19900153]),
        ([1] * 5 * 365, [365 * 44 / 12 / 1e6] * 5),
    ]
)
def series(request):
    return np.array(request.param[0]), np.array(request.param[1])


def test_timeseries_parameter_view(model, start_time, series):
    inseries = series[0]
    outseries = series[1]

    parameterset = model.parameters
    carbon = parameterset.timeseries(
        ("Emissions", "CO2"),
        "GtCO2/a",
        create_time_points(
            start_time,
            365 * 24 * 3600,
            len(outseries),
            ParameterType.AVERAGE_TIMESERIES,
        ),
        timeseries_type="average",
    )
    assert carbon.empty
    with pytest.raises(ParameterEmptyError):
        carbon.values

    carbon_writable = parameterset.timeseries(
        ("Emissions", "CO2"),
        "ktC/d",
        create_time_points(
            start_time, 24 * 3600, len(inseries), ParameterType.AVERAGE_TIMESERIES
        ),
        timeseries_type="average",
    )
    with pytest.raises(TimeseriesPointsValuesMismatchError):
        carbon_writable.values = inseries[::2]
    carbon_writable.values = inseries
    assert carbon_writable.length == len(inseries)
    np.testing.assert_allclose(
        carbon_writable.values, inseries, atol=inseries.max() * 1e-10
    )
    assert carbon.length == 5
    np.testing.assert_allclose(carbon.values, outseries, rtol=1e-3)
    with pytest.raises(ParameterTypeError):
        parameterset.scalar(("Emissions", "CO2"), "GtCO2/a")
    with pytest.raises(DimensionalityError):
        parameterset.timeseries(
            ("Emissions", "CO2"), "kg", (0,), timeseries_type="average"
        )


def test_timeseries_parameter_view_aggregation(model, start_time):
    fossil_industry_emms = np.array([0, 1, 2])
    fossil_energy_emms = np.array([2, 1, 4])
    land_emms = np.array([0.05, 0.1, 0.2])

    parameterset = model.parameters

    fossil_industry_writable = parameterset.timeseries(
        ("Emissions", "CO2", "Fossil", "Industry"),
        "GtC/yr",
        create_time_points(
            start_time,
            24 * 3600,
            len(fossil_industry_emms),
            ParameterType.AVERAGE_TIMESERIES,
        ),
        timeseries_type="average",
    )
    fossil_industry_writable.values = fossil_industry_emms

    fossil_energy_writable = parameterset.timeseries(
        ("Emissions", "CO2", "Fossil", "Energy"),
        "GtC/yr",
        create_time_points(
            start_time,
            24 * 3600,
            len(fossil_energy_emms),
            ParameterType.AVERAGE_TIMESERIES,
        ),
        timeseries_type="average",
    )
    fossil_energy_writable.values = fossil_energy_emms

    land_writable = parameterset.timeseries(
        ("Emissions", "CO2", "Land"),
        "MtC/yr",
        create_time_points(
            start_time,
            24 * 3600,
            len(fossil_energy_emms),
            ParameterType.AVERAGE_TIMESERIES,
        ),
        timeseries_type="average",
    )
    land_writable.values = land_emms * 1000

    fossil_industry = parameterset.timeseries(
        ("Emissions", "CO2", "Fossil", "Industry"),
        "GtC/yr",
        create_time_points(
            start_time,
            24 * 3600,
            len(fossil_industry_emms),
            ParameterType.AVERAGE_TIMESERIES,
        ),
        timeseries_type="average",
    )
    np.testing.assert_allclose(
        fossil_industry.values,
        fossil_industry_emms,
        atol=fossil_industry_emms.max() * 1e-10,
    )

    fossil_energy = parameterset.timeseries(
        ("Emissions", "CO2", "Fossil", "Energy"),
        "GtC/yr",
        create_time_points(
            start_time,
            24 * 3600,
            len(fossil_energy_emms),
            ParameterType.AVERAGE_TIMESERIES,
        ),
        timeseries_type="average",
    )
    np.testing.assert_allclose(fossil_energy.values, fossil_energy_emms)

    fossil = parameterset.timeseries(
        ("Emissions", "CO2", "Fossil"),
        "GtC/yr",
        create_time_points(
            start_time,
            24 * 3600,
            len(fossil_energy_emms),
            ParameterType.AVERAGE_TIMESERIES,
        ),
        timeseries_type="average",
    )
    np.testing.assert_allclose(fossil.values, fossil_industry_emms + fossil_energy_emms)

    # ensure that you can't write extra children once you've got a parent view, this
    # avoids ever having the child views being out of date
    with pytest.raises(ParameterReadError):
        parameterset.timeseries(
            ("Emissions", "CO2", "Fossil", "Transport"),
            "GtC/yr",
            create_time_points(
                start_time,
                24 * 3600,
                len(fossil_industry_emms),
                ParameterType.AVERAGE_TIMESERIES,
            ),
            timeseries_type="average",
        )

    land = parameterset.timeseries(
        ("Emissions", "CO2", "Land"),
        "GtC/yr",
        create_time_points(
            start_time, 24 * 3600, len(land_emms), ParameterType.AVERAGE_TIMESERIES
        ),
        timeseries_type="average",
    )
    np.testing.assert_allclose(land.values, land_emms)

    with pytest.raises(ParameterReadonlyError):
        parameterset.timeseries(
            ("Emissions", "CO2"),
            "GtC/yr",
            create_time_points(
                start_time,
                24 * 3600,
                len(fossil_energy_emms),
                ParameterType.AVERAGE_TIMESERIES,
            ),
            timeseries_type="average",
        ).values = np.ndarray([])

    total = parameterset.timeseries(
        ("Emissions", "CO2"),
        "GtC/yr",
        create_time_points(
            start_time,
            24 * 3600,
            len(fossil_energy_emms),
            ParameterType.AVERAGE_TIMESERIES,
        ),
        timeseries_type="average",
    )
    np.testing.assert_allclose(
        total.values, land_emms + fossil_energy_emms + fossil_industry_emms
    )


def test_generic_parameter_view(model):
    parameterset = model.parameters
    cs = parameterset.generic(("Model Options", "Generic Option"))
    with pytest.raises(ParameterAggregationError):
        parameterset.generic("Model Options")
    with pytest.raises(ParameterTypeError):
        parameterset.scalar("Model Options", "dimensionless")
    with pytest.raises(ParameterEmptyError):
        cs.value
    assert cs.empty
    cs_writable = parameterset.generic(("Model Options", "Generic Option"))
    cs_writable.value = "enabled"
    assert cs_writable.value == "enabled"
    assert not cs.empty
    assert cs.value == "enabled"
    cs_writable.value = "enabled2"
    assert cs_writable.value == "enabled2"


@pytest.mark.parametrize("ptype", ["generic", "scalar", "timeseries"])
def test_view_updates_with_new_write(ptype):
    p = ParameterSet()
    name = "example"
    if ptype == "generic":
        v = p.generic(name)
    elif ptype == "scalar":
        v = p.scalar(name, "g")
    elif ptype == "timeseries":
        tp = create_time_points(
            np.datetime64("1989-03-05"), np.timedelta64(24, "s"), 3, "point"
        )
        v = p.timeseries(name, "A", tp)

    assert v.version == 0
    if ptype == "generic":
        p.generic(name).value = 12
        assert v.value == 12
    elif ptype == "scalar":
        p.scalar(name, "kg").value = 12
        assert v.value == 12000
    elif ptype == "timeseries":
        p.timeseries(name, "mA", tp).values = np.arange(0, 3, 1)
        np.testing.assert_allclose(v.values, 10 ** -3 * np.arange(0, 3, 1))

    assert v.version == 1
    if ptype == "generic":
        v.value = 16
        assert v.value == 16
    elif ptype == "scalar":
        v.value = 1
        assert v.value == 1
    elif ptype == "timeseries":
        v.values = -1 * np.arange(0, 3, 1)
        np.testing.assert_allclose(v.values, -1 * np.arange(0, 3, 1))

    assert v.version == 2
    if ptype == "generic":
        p.generic(name).value = "hello"
        assert v.value == "hello"
    elif ptype == "scalar":
        p.scalar(name, "kg").value = -3
        assert v.value == -3000
    elif ptype == "timeseries":
        p.timeseries(name, "mA", tp).values = 3 * np.arange(0, 3, 1)
        np.testing.assert_allclose(v.values, 3 * 10 ** -3 * np.arange(0, 3, 1))

    assert v.version == 3


def test_parameter_enums():
    assert (
        ParameterType.timeseries_type_to_string(ParameterType.AVERAGE_TIMESERIES)
        == "average"
    )
    assert (
        ParameterType.timeseries_type_to_string(ParameterType.POINT_TIMESERIES)
        == "point"
    )
    with pytest.raises(ValueError, match="Timeseries type expected"):
        ParameterType.timeseries_type_to_string(ParameterType.SCALAR)

    assert (
        ParameterType.from_timeseries_type("average")
        == ParameterType.AVERAGE_TIMESERIES
    )
    assert ParameterType.from_timeseries_type("point") == ParameterType.POINT_TIMESERIES
    timeseries_type = "invalid"
    with pytest.raises(
        ValueError, match="Unknown timeseries type '{}'".format(timeseries_type)
    ):
        ParameterType.from_timeseries_type(timeseries_type)
    with pytest.raises(ValueError, match="Timeseries type expected"):
        ParameterType.from_timeseries_type(ParameterType.SCALAR)


def test_timeseries_class(model, start_time, series):
    inseries = series[0]

    parameterset = model.parameters
    parameter = parameterset.timeseries(
        "Parameter",
        "",
        create_time_points(
            start_time, 24 * 3600, len(inseries), ParameterType.AVERAGE_TIMESERIES
        ),
        timeseries_type="average",
    )
    parameter.values = inseries

    assert parameter.values.shape == inseries.shape
    assert parameter.values.nbytes == inseries.nbytes
    assert parameter.values.dtype == inseries.dtype
    assert parameter.values.ndim == 1
    assert np.all(parameter.values[:] == parameter.values[:])
    assert str(parameter.values) == "timeseries({})".format(repr(inseries))

    np.testing.assert_allclose(np.add(parameter.values, inseries), 2 * inseries)
    assert np.sum(parameter.values) == np.sum(inseries)

    out = np.empty_like(inseries, dtype=float)
    np.sin(parameter.values, out=out)
    np.testing.assert_allclose(out, np.sin(inseries))

    out0 = np.empty_like(inseries, dtype=float)
    out1 = np.empty_like(inseries, dtype=float)
    np.modf(parameter.values, out=(out0, out1))
    out = np.modf(inseries)
    np.testing.assert_equal(out[0], out0)
    np.testing.assert_equal(out[1], out1)


@pytest.mark.parametrize("view_type", ["scalar", "timeseries"])
def test_view_units(view_type):
    p = ParameterSet()
    a_unit = "kg"
    b_unit = "g"

    if view_type == "scalar":
        v1 = p.scalar("example", a_unit)
        v1.value = 2
    else:
        v1 = p.timeseries("example", a_unit, [0, 1, 2])
        v1.values = np.array([0, 1, 2])

    assert v1.unit == a_unit

    if view_type == "scalar":
        v2 = p.scalar("example", b_unit)
        assert v2.value == v1.value * 1000
    else:
        v2 = p.timeseries("example", b_unit, [0, 1, 2])
        # should we just make this `.value` too?
        assert (v2.values == v1.values * 1000).all()

    assert v2.unit == b_unit
