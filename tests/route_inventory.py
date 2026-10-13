"""Static inventory of every API route, read from the router source with `ast` (no FastAPI needed, so it runs anywhere).
Each route records its method, full path, handler, the dependencies it declares (decorator, router and parameter level,
with module-level aliases such as `_manage = Depends(require_permission(X))` resolved) and its parameters."""
import ast
import os

ROUTERS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src", "asavexa", "api", "routers")
METHODS = ("get", "post", "put", "patch", "delete")
SESSION_DEPS = {"get_current_session", "get_current_actor", "get_current_org"}


def _depends(node, aliases):
    names = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "Depends" and n.args:
            a = n.args[0]
            if isinstance(a, ast.Name):
                names.append(a.id)
            elif isinstance(a, ast.Call):
                names.append(getattr(a.func, "id", getattr(a.func, "attr", "?")) + "()")
                names.extend(_depends(a, aliases))
            elif isinstance(a, ast.Attribute):
                names.append(a.attr)
        elif isinstance(n, ast.Name) and n.id in aliases:
            names.extend(aliases[n.id])
    return names


def _const(node, default, env=None):
    """A route path as a string. Resolves literals, `A + "/x"`, and f-strings over module-level string constants."""
    env = env or {}
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _const(node.left, None, env), _const(node.right, None, env)
        return a + b if a is not None and b is not None else default
    if isinstance(node, ast.JoinedStr):
        out = ""
        for v in node.values:
            if isinstance(v, ast.Constant):
                out += str(v.value)
            elif isinstance(v, ast.FormattedValue):
                part = _const(v.value, None, env)
                if part is None:
                    return default
                out += str(part)
        return out
    return default


def inventory():
    rows = _scan_dir(ROUTERS) + _scan_main()
    return rows


def _scan_main():
    return _scan_dir(os.path.join(os.path.dirname(ROUTERS)), only="main.py", app_var=True)


def _scan_dir(directory, only=None, app_var=False):
    rows = []
    for fn in sorted(os.listdir(directory)):
        if not fn.endswith(".py") or fn == "__init__.py" or (only and fn != only):
            continue
        tree = ast.parse(open(os.path.join(directory, fn)).read())
        aliases, prefix, router_deps, env = {}, "", [], {}
        for n in tree.body:
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
                v = _const(n.value, None, env)
                if isinstance(v, str):
                    env[n.targets[0].id] = v
            elif (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Tuple) and isinstance(n.value, ast.Tuple)
                  and len(n.targets[0].elts) == len(n.value.elts)):
                for t, val in zip(n.targets[0].elts, n.value.elts):
                    v = _const(val, None, env)
                    if isinstance(t, ast.Name) and isinstance(v, str):
                        env[t.id] = v
        for n in tree.body:
            if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name):
                found = _depends(n.value, aliases)
                if found and not (isinstance(n.value, ast.Call) and getattr(n.value.func, "id", "") == "APIRouter"):
                    aliases[n.targets[0].id] = found
        routers = {"app": ("", [])} if app_var else {}   # variable -> (prefix, dependencies)
        for n in tree.body:
            if (isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and isinstance(n.value, ast.Call)
                    and getattr(n.value.func, "id", "") == "APIRouter"):
                pre, rdeps = "", []
                for k in n.value.keywords:
                    if k.arg == "prefix":
                        pre = _const(k.value, "<expr>", env)
                    if k.arg == "dependencies":
                        rdeps = _depends(k.value, aliases)
                routers[n.targets[0].id] = (pre, rdeps)
        for n in tree.body:
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for d in n.decorator_list:
                if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and isinstance(d.func.value, ast.Name)
                        and d.func.value.id in routers and d.func.attr in METHODS):
                    prefix, router_deps = routers[d.func.value.id]
                    path = _const(d.args[0], "<expr>", env) if d.args else ""
                    params = {}
                    args = n.args.args + n.args.kwonlyargs
                    defaults = [None] * (len(n.args.args) - len(n.args.defaults)) + list(n.args.defaults) + list(n.args.kw_defaults)
                    for a, dflt in zip(args, defaults):
                        params[a.arg] = _depends(dflt, aliases) if dflt is not None else []
                    own = _depends(d, aliases) + [x for v in params.values() for x in v]
                    deps = router_deps + own
                    rows.append({"own_deps": own, "file": fn, "method": d.func.attr.upper(), "path": prefix + path, "func": n.name,
                                 "deps": deps, "params": params, "node": n})
    return rows


def is_session_authenticated(row):
    s = set(row["deps"])
    return bool(s & SESSION_DEPS) or any(x.startswith("require_") for x in s)


def key(row):
    return f'{row["method"]} {row["path"]}'
