from __future__ import annotations

import sys

import click

from pia import __version__
from pia.agent import Agent
from pia.api import APIClient, APIError, Message
from pia.app import App
from pia.config import Config, load_config
from pia.display import Display
from pia.plugins import discover_plugins
from pia.profiles import ProfileManager
from pia.prompt import build_system_prompt
from pia.tools import discover_tools


def _build_app(config: Config, interactive: bool = False) -> App:
    display = Display(config)
    api = APIClient(config)

    # Placeholder registries — filled after App creation so tools/plugins can reference app
    from pia.tools import ToolRegistry
    from pia.plugins import PluginRegistry

    app = App(
        config=config,
        display=display,
        tools=ToolRegistry(),
        plugins=PluginRegistry(),
        api=api,
        interactive=interactive,
    )

    app.tools = discover_tools(app)
    app.plugins = discover_plugins(app)
    return app


@click.group(invoke_without_command=True)
@click.argument("prompt", nargs=-1)
@click.option("--model", "-m", help="Model to use.")
@click.option("--profile", "-p", help="Profile name.")
@click.option("--dry-run", is_flag=True, help="Preview commands without executing.")
@click.option("--debug", is_flag=True, help="Enable debug output.")
@click.option("--version", "-v", is_flag=True, help="Show version and exit.")
@click.pass_context
def main(ctx: click.Context, prompt: tuple[str, ...], model: str | None,
         profile: str | None, dry_run: bool, debug: bool, version: bool) -> None:
    """pia — Terminal AI agent."""
    if version:
        click.echo(f"pia {__version__}")
        return

    # Let subcommands handle themselves
    if ctx.invoked_subcommand is not None:
        return

    # Build config
    overrides: dict = {}
    if model:
        overrides["model"] = model
    if dry_run:
        overrides["dry_run"] = True
    if debug:
        overrides["debug"] = True

    config = load_config(**overrides)

    # Apply profile
    if profile:
        pm = ProfileManager(config.profiles_file)
        p = pm.get(profile)
        if p:
            config.api_url = p.api_url
            config.api_key = p.api_key
            if not model:
                config.model = p.model
        else:
            click.echo(f"Profile not found: {profile}", err=True)
            sys.exit(1)

    config.ensure_dirs()

    prompt_text = " ".join(prompt) if prompt else ""

    # Pipe mode: read stdin
    piped_input = ""
    if not sys.stdin.isatty():
        piped_input = sys.stdin.read()

    if prompt_text or piped_input:
        _single_mode(config, prompt_text, piped_input)
    else:
        _repl_mode(config)


PROVIDERS = {
    "1": {
        "name": "OpenRouter",
        "api_url": "https://openrouter.ai/api/v1",
        "model": "openai/gpt-4o",
        "key_hint": "Get one at https://openrouter.ai/keys",
    },
    "2": {
        "name": "OpenAI",
        "api_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "key_hint": "Get one at https://platform.openai.com/api-keys",
    },
    "3": {
        "name": "Anthropic",
        "api_url": "https://api.anthropic.com/v1",
        "model": "claude-sonnet-4-20250514",
        "key_hint": "Get one at https://console.anthropic.com/settings/keys",
    },
    "4": {
        "name": "Ollama",
        "api_url": "http://localhost:11434/v1",
        "model": "llama3",
        "key_hint": "",
    },
    "5": {
        "name": "Custom",
        "api_url": "",
        "model": "",
        "key_hint": "",
    },
}


@main.command()
def init() -> None:
    """Interactive setup wizard."""
    config = load_config()
    config.ensure_dirs()
    display = Display(config)

    display.info("pia setup\n")

    # Check for existing configuration
    if config.config_file.exists():
        display.info(f"Existing configuration found at {config.config_file}\n")
        reconfigure = input("Reconfigure LLM provider? [y/N] ").strip()
        if not reconfigure.lower().startswith("y"):
            display.info("Keeping existing configuration.")
            return

    click.echo("Select your LLM provider:\n")
    click.echo("  1) OpenRouter  (default — access to many models)")
    click.echo("  2) OpenAI")
    click.echo("  3) Anthropic   (Claude)")
    click.echo("  4) Ollama      (local models, no API key needed)")
    click.echo("  5) Custom endpoint")
    click.echo("")

    choice = input("Choice [1]: ").strip() or "1"
    if choice not in PROVIDERS:
        display.warn("Invalid choice, defaulting to OpenRouter.")
        choice = "1"

    provider = PROVIDERS[choice]
    display.info(f"Provider: {provider['name']}\n")

    if choice == "5":
        api_url = input("API URL: ").strip()
    else:
        api_url = provider["api_url"]

    # API key
    if choice == "4":
        api_key = "ollama"
        display.info("No API key needed for local Ollama.")
    else:
        if provider["key_hint"]:
            display.info(provider["key_hint"])
        api_key = input("API key: ").strip()
        if not api_key:
            display.warn("No API key provided. You can set PIA_API_KEY env var later.")

    # Model
    default_model = provider["model"]
    if default_model:
        model_name = input(f"Model [{default_model}]: ").strip() or default_model
    else:
        model_name = input("Model: ").strip()

    # Write config file
    config_content = f"""\
api_url = "{api_url}"
api_key = "{api_key}"
model = "{model_name}"
"""
    config.config_file.write_text(config_content)
    config.config_file.chmod(0o600)
    display.success(f"Configuration saved to {config.config_file}")


@main.command()
@click.argument("name", required=False)
@click.option("--add", is_flag=True, help="Add a new profile.")
@click.option("--remove", is_flag=True, help="Remove a profile.")
@click.option("--switch", is_flag=True, help="Switch active profile.")
def profiles(name: str | None, add: bool, remove: bool, switch: bool) -> None:
    """Manage API profiles."""
    config = load_config()
    config.ensure_dirs()
    display = Display(config)
    pm = ProfileManager(config.profiles_file)

    if add:
        from pia.profiles import Profile
        pname = name or input("Profile name: ").strip()
        if not pname:
            display.error("Profile name required.")
            return
        api_url = input("API URL [https://openrouter.ai/api/v1]: ").strip() or "https://openrouter.ai/api/v1"
        api_key = input("API key: ").strip()
        model_name = input("Model [openai/gpt-4o]: ").strip() or "openai/gpt-4o"
        pm.add(Profile(name=pname, api_url=api_url, api_key=api_key, model=model_name))
        display.success(f"Profile '{pname}' added.")
    elif remove:
        if not name:
            display.error("Profile name required.")
            return
        if pm.remove(name):
            display.success(f"Profile '{name}' removed.")
        else:
            display.error(f"Cannot remove '{name}'.")
    elif switch:
        if not name:
            display.error("Profile name required.")
            return
        if pm.switch(name):
            display.success(f"Switched to profile '{name}'.")
        else:
            display.error(f"Profile not found: {name}")
    else:
        pm.list_profiles(display)


def _single_mode(config: Config, prompt_text: str, piped_input: str) -> None:
    app = _build_app(config, interactive=False)
    app.plugins.fire("on_init")

    if not config.api_key:
        app.display.error("No API key configured. Run 'pia init' or set PIA_API_KEY.")
        sys.exit(1)

    # Combine prompt and piped input
    if piped_input and prompt_text:
        user_content = f"{prompt_text}\n\n---\n\n{piped_input}"
    elif piped_input:
        user_content = piped_input
    else:
        user_content = prompt_text

    from io import StringIO

    agent = Agent(
        config=config,
        api=app.api,
        tools=app.tools,
        plugins=app.plugins,
        output=StringIO(),
        interactive=False,
    )

    try:
        with app.display.spinner():
            response = agent.run(user_content)

        if response:
            app.display.markdown(response)

        usage = agent.last_usage
        app.display.usage(usage.prompt_tokens, usage.completion_tokens)

    except APIError as e:
        app.display.error(str(e))
        sys.exit(1)
    finally:
        app.task_manager.shutdown()
        app.plugins.fire("on_shutdown")


def _repl_mode(config: Config) -> None:
    app = _build_app(config, interactive=True)
    app.plugins.fire("on_init")

    if not config.api_key:
        app.display.error("No API key configured. Run 'pia init' or set PIA_API_KEY.")
        sys.exit(1)

    from pia.repl import REPL
    repl = REPL(app)
    repl.run()
