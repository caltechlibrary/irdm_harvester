def format_error(e):
    return (
        e.replace("\n", "-")
        .replace(":", "-")
        .replace("'", "-")
        .replace('"', "-")
        .replace("=", "-")
        .replace("(", "-")
        .replace(")", "-")
    )
