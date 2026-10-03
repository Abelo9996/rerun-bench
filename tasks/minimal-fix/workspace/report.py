# Report entry point (do not modify: imported by the nightly job).
from legacy import paginate, reportRow, totalPages


def render_page(rows, page):
    return "\n".join(reportRow(n, v).render() for n, v in paginate(rows, page, 2))


def page_count(rows):
    return totalPages(rows, 2)
