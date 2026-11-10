"""Run-wide progress accounting for sequential scrape cohorts."""
import threading


class RunProgress:
    """Count each URL once across account batches and authentication fallbacks."""

    def __init__(self, total):
        self.total = max(0, int(total))
        self._completed = set()
        self._lock = threading.Lock()

    def apply(self, event):
        """Return an event with a run-wide unique-URL progress numerator/denominator."""
        updated = dict(event)
        url = updated.get("site_url")
        with self._lock:
            if url:
                self._completed.add(url)
            progress = len(self._completed)
        updated["index"] = progress
        updated["batch_index"] = progress
        updated["N"] = self.total
        return updated
