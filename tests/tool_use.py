from src.capabilities import CapabilityResult
from src.agent.initialize_tools.tool_adapter import ToolAdapter


class _FakeAgent:
    """Small stand-in for PydanticAI's decorator-based tool registration API."""

    def __init__(self):
        self.tools = {}

    def tool_plain(self, *, name):
        """Capture registered tool callables by their model-facing name."""
        def decorator(func):
            self.tools[name] = func
            return func

        return decorator


class _FakeBroker:
    """Broker test double that records requests and returns a valid envelope."""

    def __init__(self):
        self.requests = []

    def call(self, request):
        """Record the brokered request and return its arguments as data."""
        self.requests.append(request)
        return CapabilityResult.ok(request, {"arguments": request.arguments})


def test_tool_adapter_imports():
    assert ToolAdapter is not None


def test_tool_adapter_routes_registered_calls_through_broker():
    """The adapter never calls a registered class directly at model runtime."""
    fake_agent = _FakeAgent()
    fake_broker = _FakeBroker()

    class DemoTool:
        name = "demo"
        description = "Demo tool."
        input_schema = {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to pass."},
            },
            "required": ["text"],
        }

        def call(self, tool_input):
            raise AssertionError("adapter should use broker, not direct call")

    adapter = ToolAdapter(fake_agent, broker=fake_broker)
    adapter._register_single_tool("tool.demo.demo", DemoTool)

    output = fake_agent.tools["tool_demo_demo"](text="hello")

    assert output == {
        "success": True,
        "data": {"arguments": {"text": "hello"}},
        "error": None,
    }
    assert fake_broker.requests[0].capability == "tool.demo.demo"
    assert fake_broker.requests[0].reason


def test_tool_adapter_orders_required_parameters_before_optional_defaults():
    """Schema property order should not break generated Python signatures."""
    fake_agent = _FakeAgent()
    fake_broker = _FakeBroker()

    class OrderedTool:
        name = "ordered"
        description = "Tool with optional field before required field."
        input_schema = {
            "type": "object",
            "properties": {
                "optional_value": {
                    "type": "string",
                    "description": "Optional value.",
                    "default": "safe",
                },
                "required_value": {
                    "type": "string",
                    "description": "Required value.",
                },
            },
            "required": ["required_value"],
        }

        def call(self, tool_input):
            raise AssertionError("adapter should use broker, not direct call")

    adapter = ToolAdapter(fake_agent, broker=fake_broker)
    adapter._register_single_tool("tool.demo.ordered", OrderedTool)

    output = fake_agent.tools["tool_demo_ordered"](required_value="yes")

    assert output["success"] is True
    assert fake_broker.requests[0].arguments == {"required_value": "yes"}
