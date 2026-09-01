function reviewer() {
  return {
    text: "",
    textId: "",
    busy: false,
    error: "",
    jobId: null,
    report: null,
    history: [],

    high() { return (this.report?.consensus || []).filter(c => c.priority === "high"); },
    low()  { return (this.report?.consensus || []).filter(c => c.priority === "low"); },

    async submit() {
      this.error = ""; this.report = null; this.busy = true;
      try {
        const r = await fetch("/api/review", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({text: this.text, text_id: this.textId || null}),
        });
        if (!r.ok) throw new Error(await r.text());
        const {job_id} = await r.json();
        this.jobId = job_id;
        await this.poll(job_id);
        await this.loadHistory();
      } catch (e) {
        this.error = String(e);
      } finally {
        this.busy = false;
      }
    },

    async poll(job_id) {
      for (let i = 0; i < 300; i++) {
        await new Promise(r => setTimeout(r, 2000));
        const r = await fetch("/api/review/" + job_id);
        if (!r.ok) throw new Error("poll failed");
        const j = await r.json();
        if (j.status === "done") { this.report = j.report; return; }
        if (j.status === "error") throw new Error(j.error || "review error");
      }
      throw new Error("timeout");
    },

    async loadJob(job_id) {
      const r = await fetch("/api/review/" + job_id);
      if (!r.ok) return;
      const j = await r.json();
      if (j.report) { this.jobId = job_id; this.report = j.report; window.scrollTo({top: 0, behavior: "smooth"}); }
    },

    async loadHistory() {
      try {
        const r = await fetch("/api/history");
        if (r.ok) this.history = await r.json();
      } catch {}
    },
  };
}
