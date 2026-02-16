from typing import Any, Dict, Tuple, List

def _shape_fill_and_prune(template: Any, data: Any, path: str = "") -> Tuple[Any, List[str]]:
    """
    Enforce that `data` matches the key-structure of `template`.
    - If template is a dict: output dict with exactly those keys (recursive)
    - If template is a list: accept list, but do not enforce item shape deeply (MVP)
    - Otherwise: accept scalar, or null if missing/invalid
    Returns: (normalized_data, warnings)
    """
    warnings: List[str] = []

    # Dict shape
    if isinstance(template, dict):
        out: Dict[str, Any] = {}
        if not isinstance(data, dict):
            data = {}
            warnings.append(f"{path or 'data'}: expected object, got non-object -> set to nulls")

        for k, sub_template in template.items():
            sub_path = f"{path}.{k}" if path else k
            if isinstance(data, dict) and k in data:
                out[k], w = _shape_fill_and_prune(sub_template, data.get(k), sub_path)
                warnings.extend(w)
            else:
                # missing -> null / empty structure
                out[k], w = _shape_fill_and_prune(sub_template, None, sub_path)
                warnings.extend(w)

        return out, warnings

    # List shape (MVP: ensure list or null)
    if isinstance(template, list):
        if data is None:
            return [], warnings
        if not isinstance(data, list):
            warnings.append(f"{path}: expected array, got non-array -> set to []")
            return [], warnings
        return data, warnings

    # Scalar shape (template is usually None)
    # If missing -> None
    return data if data is not None else None, warnings


def enforce_shape(schema_template: Dict[str, Any], data: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    normalized, warnings = _shape_fill_and_prune(schema_template, data, path="")
    if not isinstance(normalized, dict):
        # should never happen
        return {}, warnings + ["data: normalization failed"]
    return normalized, warnings