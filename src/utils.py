import os


def smart_file_search(cache, query):
    """
    Search a list of file paths (cache) using a smart search algorithm.
    Prioritizes exact basename matches, then exact path matches,
    then case-insensitive substring matches, then fuzzy (subsequence) matches.
    """
    if not query:
        return cache

    query = query.lower()
    results = []

    for path in cache:
        lower_path = path.lower()
        basename = os.path.basename(lower_path)

        score = 0
        if query == basename:
            score = 100
        elif query == lower_path:
            score = 90
        elif basename.startswith(query):
            score = 80
        elif query in basename:
            score = 50
        elif lower_path.startswith(query):
            score = 40
        elif query in lower_path:
            score = 25
        else:
            # Fuzzy match: subsequence
            idx = 0
            for char in lower_path:
                if char == query[idx]:
                    idx += 1
                    if idx == len(query):
                        score = 10
                        break

        if score > 0:
            results.append((score, path))

    # Sort results:
    # 1. Highest score first (descending) -> -score
    # 2. Shorter length first (ascending) -> len(path)
    # 3. Alphabetical order (ascending) -> path
    results.sort(key=lambda x: (-x[0], len(x[1]), x[1]))

    return [item[1] for item in results]
