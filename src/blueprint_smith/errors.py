class SpecError(ValueError):
    """The JSON spec is malformed or asks for something unsupported."""


class BuildError(RuntimeError):
    """A generated blueprint failed validation (overlap, unknown entity, power, inserter wiring...)."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))
