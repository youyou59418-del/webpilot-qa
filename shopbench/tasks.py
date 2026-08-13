from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Difficulty = Literal["easy", "medium", "hard"]


class BenchTask(BaseModel):
    """One fixed, independently repeatable ShopBench task."""

    model_config = ConfigDict(extra="forbid")

    id: str
    difficulty: Difficulty
    start_path: str = "/?reset=1"
    goal: str
    expected_state: dict[str, Any]
    risk_level: Literal["L0", "L1", "L2", "L3"]
    modules: list[str] = Field(min_length=1)


def _task(
    difficulty: Difficulty,
    number: int,
    goal: str,
    expected_state: dict[str, Any],
    risk_level: Literal["L0", "L1", "L2", "L3"],
    modules: list[str],
) -> BenchTask:
    prefix = {"easy": "E", "medium": "M", "hard": "H"}[difficulty]
    return BenchTask(
        id=f"{prefix}{number:02d}",
        difficulty=difficulty,
        goal=goal,
        expected_state=expected_state,
        risk_level=risk_level,
        modules=modules,
    )


def _easy_tasks() -> list[BenchTask]:
    tasks: list[BenchTask] = [
        _task("easy", 1, "Log in with the visible demo account and verify the account banner.", {"logged_in": True}, "L1", ["login"]),
        _task("easy", 2, "Open the Catalog tab and verify the product table is visible.", {"active_tab": "Catalog"}, "L0", ["tabs", "tables"]),
        _task("easy", 3, "Open the Orders tab and verify its empty-state table is visible.", {"active_tab": "Orders"}, "L0", ["tabs", "tables"]),
        _task("easy", 4, "Open the Profile tab and verify the address form is visible.", {"active_tab": "Profile"}, "L0", ["tabs", "forms"]),
        _task("easy", 5, "Open the help dialog and verify the dialog title.", {"dialog_open": "ShopBench help"}, "L0", ["dialog"]),
        _task("easy", 6, "Show the loading state and verify the loading indicator appears.", {"loading_visible": True}, "L0", ["loading"]),
        _task("easy", 7, "Show the controlled error state and verify the retry button appears.", {"error_visible": True}, "L0", ["error"]),
        _task("easy", 8, "Refresh the featured offer and verify a toast is shown.", {"toast": "Featured offer refreshed"}, "L0", ["dynamic_dom", "toast"]),
        _task("easy", 9, "Move to inventory page two and verify the page indicator.", {"inventory_page": 2}, "L0", ["tables", "pagination"]),
        _task("easy", 10, "Reset the benchmark state and verify the cart count is zero.", {"cart_count": 0}, "L0", ["cart"]),
    ]
    for offset, query in enumerate(["laptop", "phone", "headphones", "monitor", "keyboard", "mouse", "camera", "watch", "tablet", "speaker"], start=11):
        tasks.append(_task("easy", offset, f"Search the catalog for {query} and verify matching results are shown.", {"search": query, "results_visible": True}, "L1", ["search"]))
    for offset, category in enumerate(["Electronics", "Office", "Wearables", "Audio", "Home", "All"], start=21):
        tasks.append(_task("easy", offset, f"Filter the catalog to {category} and verify the active category label.", {"category": category}, "L1", ["filter"]))
    tasks.extend([
        _task("easy", 27, "Enable the in-stock-only filter and verify the filter chip.", {"in_stock_only": True}, "L1", ["filter"]),
        _task("easy", 28, "Sort the catalog by price ascending and verify the sort selection.", {"sort": "Price: low to high"}, "L1", ["tables", "filter"]),
        _task("easy", 29, "Add Laptop Pro to the cart and verify the cart count is one.", {"cart_count": 1, "cart_contains": "Laptop Pro"}, "L1", ["cart"]),
        _task("easy", 30, "Fill the shipping city with Hangzhou and verify the saved profile toast.", {"profile_city": "Hangzhou", "toast": "Profile saved"}, "L1", ["forms", "toast"]),
    ])
    return tasks


def _medium_tasks() -> list[BenchTask]:
    products = ["Laptop Pro", "Phone Max", "Headphones Studio", "Monitor 4K", "Keyboard Pro", "Mouse Air", "Camera Lite", "Watch Active", "Tablet Note", "Speaker Mini"]
    tasks: list[BenchTask] = []
    for number, product in enumerate(products, start=1):
        tasks.append(_task("medium", number, f"Search for {product}, add it to the cart, and verify the cart contains exactly one item.", {"search": product, "cart_count": 1, "cart_contains": product}, "L1", ["search", "cart", "toast"]))
    categories = ["Electronics", "Office", "Wearables", "Audio", "Home"]
    for number in range(11, 21):
        category = categories[(number - 11) % len(categories)]
        tasks.append(_task("medium", number, f"Filter to {category}, turn on in-stock-only, sort by price, and verify the catalog is still populated.", {"category": category, "in_stock_only": True, "sort": "Price: low to high", "results_visible": True}, "L1", ["filter", "tables"]))
    for number in range(21, 26):
        city = ["Beijing", "Shanghai", "Shenzhen", "Chengdu", "Hangzhou"][number - 21]
        tasks.append(_task("medium", number, f"Log in, save a profile address in {city}, and verify the profile saved toast.", {"logged_in": True, "profile_city": city, "toast": "Profile saved"}, "L1", ["login", "forms", "toast"]))
    for number in range(26, 31):
        tasks.append(_task("medium", number, "Move to inventory page two, open a product detail dialog, and verify the product title is present.", {"inventory_page": 2, "dialog_open": "Product details"}, "L0", ["tables", "pagination", "dialog"]))
    for number in range(31, 36):
        tasks.append(_task("medium", number, "Trigger loading, wait for catalog controls to return, refresh featured offers, and verify the refresh toast.", {"loading_completed": True, "toast": "Featured offer refreshed"}, "L0", ["loading", "dynamic_dom", "toast"]))
    for number in range(36, 41):
        tasks.append(_task("medium", number, "Trigger the controlled error state, recover using Retry, and verify the error state is cleared.", {"error_visible": False}, "L1", ["error", "dynamic_dom"]))
    return tasks


def _hard_tasks() -> list[BenchTask]:
    products = ["Laptop Pro", "Phone Max", "Headphones Studio", "Monitor 4K", "Keyboard Pro", "Mouse Air", "Camera Lite", "Watch Active", "Tablet Note", "Speaker Mini"]
    cities = ["Beijing", "Shanghai", "Shenzhen", "Chengdu", "Hangzhou", "Nanjing"]
    tasks: list[BenchTask] = []
    for number in range(1, 16):
        product = products[(number - 1) % len(products)]
        city = cities[(number - 1) % len(cities)]
        tasks.append(_task("hard", number, f"Log in, search for {product}, enable in-stock-only, add the result to the cart, save shipping city {city}, and verify cart count one plus the saved-profile toast.", {"logged_in": True, "search": product, "in_stock_only": True, "cart_count": 1, "profile_city": city, "toast": "Profile saved"}, "L1", ["login", "search", "filter", "cart", "forms", "toast"]))
    for number in range(16, 26):
        product = products[(number - 16) % len(products)]
        tasks.append(_task("hard", number, f"Open Catalog, sort by price, go to inventory page two, inspect product details, add {product} to the cart, then open checkout confirmation without confirming it.", {"sort": "Price: low to high", "inventory_page": 2, "cart_contains": product, "dialog_open": "Checkout confirmation"}, "L3", ["tabs", "tables", "pagination", "dialog", "cart"]))
    for number in range(26, 31):
        tasks.append(_task("hard", number, "Log in, trigger loading and the controlled error state, recover with Retry, refresh featured offers, and verify the final toast and account banner.", {"logged_in": True, "error_visible": False, "toast": "Featured offer refreshed"}, "L1", ["login", "loading", "error", "dynamic_dom", "toast"]))
    return tasks


TASKS = _easy_tasks() + _medium_tasks() + _hard_tasks()


def all_tasks() -> list[BenchTask]:
    return list(TASKS)


def by_difficulty(difficulty: Difficulty | None = None) -> list[BenchTask]:
    return [task for task in TASKS if difficulty is None or task.difficulty == difficulty]


def get_task(task_id: str) -> BenchTask | None:
    return next((task for task in TASKS if task.id == task_id), None)
