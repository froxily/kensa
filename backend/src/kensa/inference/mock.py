"""Deterministic provider for CI, tests and model-free demos.

It returns the rule-based response the pipeline supplies in ``request.hints["mock_response"]``,
so "mock" investigations are honest rules-only diagnoses, labelled as such everywhere.
"""

from pydantic import BaseModel, ValidationError

from kensa.inference.base import MalformedOutputError, StructuredRequest, StructuredResult


class MockProvider:
    name = "mock"
    model: str | None = None

    def generate_structured[T: BaseModel](
        self, request: StructuredRequest[T]
    ) -> StructuredResult[T]:
        response = request.hints.get("mock_response")
        if response is None:
            raise MalformedOutputError(f"no deterministic response for task '{request.task}'")
        try:
            value = request.schema.model_validate(response)
        except ValidationError as exc:
            raise MalformedOutputError(str(exc)) from exc
        return StructuredResult(
            value=value,
            provider=self.name,
            model=None,
            prompt_tokens=None,
            output_tokens=None,
            duration_ms=0,
            attempts=1,
        )
