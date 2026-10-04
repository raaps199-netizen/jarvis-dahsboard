export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ error: "Gunakan metode POST." });
  }

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return res.status(503).json({ error: "Backend belum dikonfigurasi. Tambahkan GEMINI_API_KEY di Vercel Environment Variables." });
  }

  const question = typeof req.body?.question === "string" ? req.body.question.trim() : "";
  if (!question) return res.status(400).json({ error: "Pertanyaan belum diisi." });
  if (question.length > 700) return res.status(400).json({ error: "Pertanyaan maksimal 700 karakter." });

  try {
    const response = await fetch("https://generativelanguage.googleapis.com/v1beta/interactions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-goog-api-key": apiKey
      },
      body: JSON.stringify({
        model: "gemini-3.8-flash",
        input: question,
        system_instruction: "Kamu adalah J.A.R.V.I.S. Research Assistant. Jawab dalam bahasa Indonesia yang jelas, analitis, dan terstruktur. Untuk pertanyaan faktual atau terkini, gunakan Google Search grounding yang tersedia. Bedakan fakta, dugaan, dan ketidakpastian. Sertakan tanggal jika relevan. Jangan mengarang sumber. Buat jawaban dengan ringkasan, penjelasan, dan poin penting bila cocok.",
        tools: [{ type: "google_search" }],
        generation_config: { temperature: 0.35, max_output_tokens: 1800 },
        store: false
      })
    });

    const data = await response.json();
    if (!response.ok) {
      const message = data?.error?.message || "Gemini Interactions API gagal memproses permintaan.";
      const status = response.status === 429 ? 429 : 502;
      return res.status(status).json({ error: message.slice(0, 350) });
    }

    const steps = Array.isArray(data.steps) ? data.steps : [];
    const answer = steps
      .filter(step => step.type === "model_output")
      .flatMap(step => Array.isArray(step.content) ? step.content : [])
      .filter(part => part.type === "text" && typeof part.text === "string")
      .map(part => part.text)
      .join("\n")
      .trim();

    const sources = [];
    for (const step of steps) {
      const candidates = [
        ...(Array.isArray(step?.content) ? step.content : []),
        ...(Array.isArray(step?.output) ? step.output : [])
      ];
      for (const item of candidates) {
        const web = item?.web || item?.grounding_chunk?.web || item?.source;
        if (web?.uri && web?.title) sources.push({ title: web.title, url: web.uri });
      }
    }
    const uniqueSources = sources
      .filter((item, index, all) => all.findIndex(other => other.url === item.url) === index)
      .slice(0, 8);

    if (!answer) {
      return res.status(502).json({ error: "Gemini tidak mengembalikan jawaban teks. Coba pertanyaan lain." });
    }
    return res.status(200).json({ answer, sources: uniqueSources });
  } catch (error) {
    return res.status(500).json({ error: "Tidak dapat menghubungi Gemini saat ini. Periksa koneksi dan konfigurasi backend." });
  }
}
