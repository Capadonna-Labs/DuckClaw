"""LLM tool-binding cache for agent node."""

from __future__ import annotations

from duckclaw.workers.factory_graph_context import WorkerGraphContext
from duckclaw.workers.tool_binding import tool_choice_function as _tool_choice_function


def build_agent_llm_bind(ctx: WorkerGraphContext) -> None:
    llm = ctx.llm
    tools = ctx.tools
    tools_by_name = ctx.tools_by_name
    tools_sandbox_off = ctx.tools_sandbox_off
    tools_by_name_sandbox_off = ctx.tools_by_name_sandbox_off
    _tools_for_llm_bind = ctx.tools_for_llm_bind
    _tools_sandbox_off_bind = ctx.tools_sandbox_off_bind
    if llm is None:
        return
    from duckclaw.integrations.llm_providers import bind_tools_with_parallel_default as _bind_tools

    llm_with_tools_on = _bind_tools(llm, _tools_for_llm_bind)
    llm_with_tools_off = _bind_tools(llm, _tools_sandbox_off_bind)

    has_read_sql = "read_sql" in tools_by_name
    has_admin_sql = "admin_sql" in tools_by_name
    _sandbox_exec_tool = (
        "execute_sandbox_script"
        if "execute_sandbox_script" in tools_by_name
        else "run_sandbox"
    )
    has_run_sandbox = _sandbox_exec_tool in tools_by_name
    tool_choice_inspect_schema = _tool_choice_function("inspect_schema")
    tool_choice_read_sql = _tool_choice_function("read_sql")
    tool_choice_admin_sql = _tool_choice_function("admin_sql")
    tool_choice_run_sandbox = _tool_choice_function(_sandbox_exec_tool)

    llm_force_schema_on = _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_inspect_schema)
    llm_force_schema_off = _bind_tools(
        llm, _tools_sandbox_off_bind, tool_choice=tool_choice_inspect_schema
    )
    llm_force_read_sql_on = _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_read_sql)
    llm_force_read_sql_off = _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_read_sql)
    llm_force_admin_sql_on = (
        _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_admin_sql) if has_admin_sql else None
    )
    llm_force_admin_sql_off = (
        _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_admin_sql)
        if has_admin_sql
        else None
    )
    llm_force_run_sandbox_on = (
        _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_run_sandbox)
        if has_run_sandbox
        else None
    )
    llm_force_run_sandbox_off = (
        _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_run_sandbox)
        if "run_sandbox" in tools_by_name_sandbox_off
        else None
    )

    has_tavily = "tavily_search" in tools_by_name
    tool_choice_tavily = _tool_choice_function("tavily_search")
    llm_force_tavily_on = (
        _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_tavily) if has_tavily else None
    )
    llm_force_tavily_off = (
        _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_tavily) if has_tavily else None
    )

    # Local Comfy (`generate_visual_asset`) or Fal Flux (`generate_flux_image`).
    primary_visual_tool = (
        "generate_visual_asset"
        if "generate_visual_asset" in tools_by_name
        else ("generate_flux_image" if "generate_flux_image" in tools_by_name else None)
    )
    has_generate_visual = primary_visual_tool is not None
    tool_choice_generate_visual = (
        _tool_choice_function(primary_visual_tool) if primary_visual_tool else None
    )
    llm_force_generate_visual_on = (
        _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_generate_visual)
        if primary_visual_tool
        else None
    )
    llm_force_generate_visual_off = (
        _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_generate_visual)
        if primary_visual_tool and primary_visual_tool in tools_by_name_sandbox_off
        else None
    )

    _reddit_tool_names = sorted(k for k in tools_by_name if (k or "").startswith("reddit_"))
    has_reddit_tools = bool(_reddit_tool_names)

    llm_force_reddit_post_on = (
        _bind_tools(llm, tools, tool_choice=_tool_choice_function("reddit_get_post"))
        if "reddit_get_post" in tools_by_name
        else None
    )
    llm_force_reddit_post_off = (
        _bind_tools(llm, tools_sandbox_off, tool_choice=_tool_choice_function("reddit_get_post"))
        if "reddit_get_post" in tools_by_name_sandbox_off
        else None
    )
    llm_force_reddit_search_on = (
        _bind_tools(llm, tools, tool_choice=_tool_choice_function("reddit_search_reddit"))
        if "reddit_search_reddit" in tools_by_name
        else None
    )
    llm_force_reddit_search_off = (
        _bind_tools(llm, tools_sandbox_off, tool_choice=_tool_choice_function("reddit_search_reddit"))
        if "reddit_search_reddit" in tools_by_name_sandbox_off
        else None
    )
    _reddit_fallback_nm = None
    if has_reddit_tools and not llm_force_reddit_post_on and not llm_force_reddit_search_on:
        _reddit_fallback_nm = _reddit_tool_names[0]
    llm_force_reddit_fallback_on = (
        _bind_tools(llm, tools, tool_choice=_tool_choice_function(_reddit_fallback_nm))
        if _reddit_fallback_nm and _reddit_fallback_nm in tools_by_name
        else None
    )
    llm_force_reddit_fallback_off = (
        _bind_tools(llm, tools_sandbox_off, tool_choice=_tool_choice_function(_reddit_fallback_nm))
        if _reddit_fallback_nm and _reddit_fallback_nm in tools_by_name_sandbox_off
        else None
    )


    ctx.agent_bind = {
        "llm_with_tools_on": llm_with_tools_on,
        "llm_with_tools_off": llm_with_tools_off,
        "llm_force_schema_on": llm_force_schema_on,
        "llm_force_schema_off": llm_force_schema_off,
        "llm_force_read_sql_on": llm_force_read_sql_on,
        "llm_force_read_sql_off": llm_force_read_sql_off,
        "llm_force_admin_sql_on": llm_force_admin_sql_on,
        "llm_force_admin_sql_off": llm_force_admin_sql_off,
        "llm_force_run_sandbox_on": llm_force_run_sandbox_on,
        "llm_force_run_sandbox_off": llm_force_run_sandbox_off,
        "llm_force_tavily_on": llm_force_tavily_on,
        "llm_force_tavily_off": llm_force_tavily_off,
        "llm_force_generate_visual_on": llm_force_generate_visual_on,
        "llm_force_generate_visual_off": llm_force_generate_visual_off,
        "llm_force_reddit_post_on": llm_force_reddit_post_on,
        "llm_force_reddit_post_off": llm_force_reddit_post_off,
        "llm_force_reddit_search_on": llm_force_reddit_search_on,
        "llm_force_reddit_search_off": llm_force_reddit_search_off,
        "llm_force_reddit_fallback_on": llm_force_reddit_fallback_on,
        "llm_force_reddit_fallback_off": llm_force_reddit_fallback_off,
        "has_read_sql": has_read_sql,
        "has_tavily": has_tavily,
        "has_generate_visual": has_generate_visual,
        "primary_visual_tool": primary_visual_tool,
        "has_reddit_tools": has_reddit_tools,
        "has_run_sandbox": has_run_sandbox,
    }
