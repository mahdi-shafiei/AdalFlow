"""DataClassParser will help users interact with LLMs even better than JsonOutputParser and YamlOutputParser with DataClass."""

from dataclasses import is_dataclass
from typing import Any, Literal, List, Optional
import logging

from adalflow.core.prompt_builder import Prompt
from adalflow.core.component import DataComponent
from adalflow.core.string_parser import YamlParser, JsonParser
from adalflow.core.base_data_class import DataClass, DataClassFormatType
from adalflow.core.base_data_class import ExcludeType, IncludeType


__all__ = ["DataClassParser"]

log = logging.getLogger(__name__)

JSON_OUTPUT_FORMAT = r"""Your output should be formatted as a standard JSON instance with the following schema:
```
{{schema}}
```
-Make sure to always enclose the JSON output in triple backticks (```). Please do not add anything other than valid JSON output!
-Use double quotes for the keys and string values.
-DO NOT mistake the "properties" and "type" in the schema for the actual fields in the JSON output.
-Follow the JSON formatting conventions."""

YAML_OUTPUT_FORMAT = r"""Your output should be formatted as a standard YAML instance with the following schema:
```
{{schema}}
```
-Make sure to always enclose the YAML output in triple backticks (```). Please do not add anything other than valid YAML output!
-Follow the YAML formatting conventions with an indent of 2 spaces.
-DO NOT mistak the "properties" and "type" in the schema for the actual fields in the YAML output.
-Quote the string values properly."""

EXAMPLES_FORMAT = r"""
{% if examples %}
{% for example in examples %}
{{example}}
__________
{% endfor %}
{% endif %}
"""


class DataClassParser(DataComponent):
    __doc__ = r"""Made the structured output even simpler compared with JsonOutputParser and YamlOutputParser.

        1. Understands __input_fields__ and __output_fields__ from the DataClass (no need to use include/exclude to decide fields).
        2. User can choose to save the `task_desc` in the DataClass and use it in the prompt.

        Example:

        .. code-block:: python

            @dataclass
            class BasicQAOutput(adal.DataClass):
                explanation: str = field(
                    metadata={"desc": "A brief explanation of the concept in one sentence."}
                )
                example: str = field(
                    metadata={"desc": "An example of the concept in a sentence."}
                )
                # Control output fields order
                __output_fields__ = ["explanation", "example"]

            # Define the template using jinja2 syntax
            qa_template = "<SYS>
            You are a helpful assistant.
            <OUTPUT_FORMAT>
            {{output_format_str}}
            </OUTPUT_FORMAT>
            </SYS>
            <USER> {{input_str}} </USER>"

            parser = adal.DataClassParser(data_class=BasicQAOutput, return_data_class=True)

            # Set up the generator with model, template, and parser
            self.generator = adal.Generator(
                model_client=model_client,
                model_kwargs=model_kwargs,
                template=qa_template,
                prompt_kwargs={"output_format_str": parser.get_output_format_str()},
                output_processors=parser,
            )
        """

    def __init__(
        self,
        data_class: DataClass,
        return_data_class: bool = True,
        format_type: Literal["yaml", "json"] = "json",
    ):
        super().__init__()
        if not is_dataclass(data_class):
            raise ValueError("data_class must be a dataclass.")

        if not issubclass(data_class, DataClass):
            raise ValueError("data_class must be a subclass of DataClass.")

        self._return_data_class = return_data_class
        self._input_fields = data_class.get_input_fields()
        self._output_fields = data_class.get_output_fields()
        if format_type not in ["yaml", "json"]:
            raise ValueError("Invalid format type.")
        self._format_type = format_type
        self._data_class: DataClass = data_class
        self._output_processor = YamlParser() if format_type == "yaml" else JsonParser()
        self.output_format_prompt = (
            Prompt(template=YAML_OUTPUT_FORMAT)
            if format_type == "yaml"
            else Prompt(template=JSON_OUTPUT_FORMAT)
        )

    def get_input_format_str(self) -> str:
        r"""Return the formatted instructions to use in prompt for the input format."""
        if self._format_type == "yaml":
            return self._data_class.to_yaml_signature(include=self._input_fields)
        else:
            return self._data_class.to_json_signature(include=self._input_fields)

    def get_output_format_str(self) -> str:
        r"""Return the formatted instructions to use in prompt for the output format."""
        output_format_str = None
        if self._format_type == "yaml":
            schema = self._data_class.to_yaml_signature(include=self._output_fields)
            output_format_str = Prompt(template=YAML_OUTPUT_FORMAT)(schema=schema)
        else:
            schema = self._data_class.to_json_signature(include=self._output_fields)
            output_format_str = Prompt(template=JSON_OUTPUT_FORMAT)(schema=schema)
        return output_format_str

    def get_input_str(self, input: DataClass) -> str:
        r"""Return the formatted input string."""
        if not isinstance(input, self._data_class):
            raise ValueError("input must be an instance of the data_class.")
        if self._format_type == "yaml":
            return input.to_yaml(include=self._input_fields)
        else:
            return input.to_json(include=self._input_fields)

    def get_task_desc_str(self) -> str:
        r"""Return the task description string."""
        return self._data_class.get_task_desc()

    def get_examples_str(
        self,
        examples: List[DataClass],
        include: Optional[IncludeType] = None,
        exclude: Optional[ExcludeType] = None,
    ) -> str:
        r"""Return the examples string."""
        str_examples = []
        if examples and len(examples) > 0:
            for example in examples:
                per_example_str = example.format_example_str(
                    format_type=(
                        DataClassFormatType.EXAMPLE_YAML
                        if self._format_type == "yaml"
                        else DataClassFormatType.EXAMPLE_JSON
                    ),
                    exclude=exclude,
                    include=include,
                )
                str_examples.append(per_example_str)

        examples_str = Prompt(template=EXAMPLES_FORMAT)(examples=str_examples)
        return examples_str

    def call(self, input: str) -> Any:
        r"""Parse the output string to the desired format and return the parsed output."""
        try:
            output_dict = self._output_processor(input)
            if self._return_data_class:
                return self._data_class.from_dict(output_dict)
            return output_dict
        except Exception as e:
            log.error(f"Error at parsing output: {e}")
            raise ValueError(f"Error: {e}")

    def _extra_repr(self) -> str:
        s = f"data_class={self._data_class.__name__}, format_type={self._format_type},\
            return_data_class={self._return_data_class}, input_fields={self._input_fields},\
            output_fields={self._output_fields}"
        return s
