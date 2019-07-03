# openscm/adapters/cscmadapter.py

from ..adapter import Adapter

YEAR = 365 * 24 * 60 * 60  # example time step length as used below

class CSCMAdapter(Adapter):


    def _initialize_model(self) -> None:
        pass
        # TODO Initialize the model
        # TODO Set default parameter values:
        """
        self._parameters.get_writable_scalar_view(
            ("MyModel", "Specific Parameter"), ("World",), "Unit"
        ).set(DEFAULT_VALUE)
        """

    def _initialize_model_input(self) -> None:
        pass
    """
    TODO Initialize model input by reading input parameters from
    :class:`self._parameters
    <~openscm.adapter.Adapter._parameters>` (see below).
    """

    def _reset(self) -> None:
        pass
    # TODO Reset the model


    def _run(self) -> None:
        pass
    """
    TODO Run the model and write output parameters to
    :class:`self._output <~openscm.adapter.Adapter._output>`
    (see below).
    """

    def _step(self) -> None:
        pass
    """
    TODO Do a single time step and write corresponding output
    parameters to :class:`self._output
    <~openscm.adapter.Adapter._output>` (see below).
    """
       #self._current_time += YEAR


    def _shutdown(self) -> None:
        pass
    # TODO Shut down model
