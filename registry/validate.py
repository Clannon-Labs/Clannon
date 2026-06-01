from __future__ import annotations

from pathlib import Path
from typing import Type, Dict, Any

class Validator:
    # =====================================================
    # Shared Validation
    # =====================================================

    @staticmethod
    def _validate_common(cls: Type) -> None:
        """
        Validate shared structural requirements.

        Every registered object MUST contain:
            - name
            - description
            - input_schema
            - output_schema
            - call()

        Validation is intentionally structural
        (duck-typing style).

        Users are NOT forced to inherit from a base class.
        """

        required_fields = [
            "name",
            "description",
            "input_schema",
            "output_schema",
        ]

        # -------------------------------------------------
        # Required field existence
        # -------------------------------------------------

        for field_name in required_fields:
            if not hasattr(cls, field_name):
                raise TypeError(
                    f"{cls.__name__} missing required field: '{field_name}'"
                )

        # -------------------------------------------------
        # Name
        # -------------------------------------------------

        if not isinstance(cls.name, str):
            raise TypeError(
                f"{cls.__name__}.name must be str"
            )

        if not cls.name.strip():
            raise ValueError(
                f"{cls.__name__}.name cannot be empty"
            )

        # -------------------------------------------------
        # Description
        # -------------------------------------------------

        if not isinstance(cls.description, str):
            raise TypeError(
                f"{cls.__name__}.description must be str"
            )

        if not cls.description.strip():
            raise ValueError(
                f"{cls.__name__}.description cannot be empty"
            )

        # -------------------------------------------------
        # Input schema
        # -------------------------------------------------

        if not isinstance(cls.input_schema, dict):
            raise TypeError(
                f"{cls.__name__}.input_schema must be a dict"
            )

        # -------------------------------------------------
        # Output schema
        # -------------------------------------------------

        if not isinstance(cls.output_schema, dict):
            raise TypeError(
                f"{cls.__name__}.output_schema must be a dict"
            )

        # -------------------------------------------------
        # call()
        # -------------------------------------------------

        if not callable(getattr(cls, "call", None)):
            raise TypeError(
                f"{cls.__name__} must implement call() method"
            )

    # =====================================================
    # Tool Validation
    # =====================================================

    @staticmethod
    def validate_tool(cls: Type) -> None:
        """
        Tool-specific validation.

        Tools currently only require
        common validation.
        """

        Validator._validate_common(cls)

    # =====================================================
    # Expert Validation
    # =====================================================

    @staticmethod
    def validate_expert(cls: Type) -> None:
        """
        Expert-specific validation.

        Experts MUST define:
            instruction_files: List[str]

        Each file:
            - must end in .md
            - must exist
        """

        Validator._validate_common(cls)

        # Get the instruction files if they exist, else give None
        instruction_files = getattr(
            cls,
            "instruction_files",
            None
        )

        # -------------------------------------------------
        # instruction_files existence/type
        # -------------------------------------------------

        if instruction_files is None:
            raise ValueError(
                f"{cls.__name__} missing instruction_files"
            )

        if not isinstance(instruction_files, list):
            raise TypeError(
                f"{cls.__name__}.instruction_files must be List[str]"
            )

        if len(instruction_files) == 0:
            raise ValueError(
                f"{cls.__name__} must define at least one .md file"
            )

        # -------------------------------------------------
        # File validation
        # -------------------------------------------------

        for file_path in instruction_files:
            if not isinstance(file_path, str):
                raise TypeError(
                    f"instruction file path must be str"
                )

            if not file_path.endswith(".md"):
                raise ValueError(
                    f"{file_path} is not a .md file"
                )

            if not Path(file_path).exists():
                raise FileNotFoundError(
                    f"Instruction file not found: {file_path}"
                )
