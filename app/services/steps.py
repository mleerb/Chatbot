FIXED_LABELS = {
    "search_current_question": "Searching the web",
    "generate_image": "Creating an image",
    "write_todos": "Planning",
    "task": "Working on a subtask",
}
FILE_LABELS = {
    "get_outline": "Reading",
    "read_page": "Reading",
    "search_in_file": "Searching",
    "edit_uploaded_file": "Editing",
}


def step_label(call: dict, filenames: dict[str, str]) -> str:
    name = call.get("name", "")
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    if name in FIXED_LABELS:
        return FIXED_LABELS[name]
    if name == "create_text_file":
        filename = str(args.get("filename") or "").strip()
        return f"Creating {filename}" if filename else "Creating a file"
    if name in FILE_LABELS:
        filename = filenames.get(str(args.get("file_id") or ""))
        if filename is None and len(filenames) == 1:
            filename = next(iter(filenames.values()))
        return f"{FILE_LABELS[name]} {filename}" if filename else f"{FILE_LABELS[name]} your file"
    return "Working"
