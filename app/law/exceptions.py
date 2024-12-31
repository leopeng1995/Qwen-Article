from typing import Any


class ToolException(Exception):

    def __init__(self, traceback: str, ename: str, evalue: str) -> None:
        """Initialize the error."""
        super().__init__(traceback)
        self.traceback = traceback
        self.ename = ename
        self.evalue = evalue
    
    def __reduce__(self) -> tuple[Any]:
        """Reduce implementation."""
        return type(self), (self.traceback, self.ename, self.evalue)  # type:ignore[return-value]

    def __str__(self) -> str:
        """Str repr."""
        if self.traceback:
            return self.traceback
        else:
            return f"{self.ename}: {self.evalue}"
