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
    const response = await fetch(
      "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": apiKey
        },
        body: JSON.stringify({
          system_instruction: {
            parts: [{
              text: "Kamu adalah J.A.R.V.I.S. Research Assistant. Jawab dalam bahasa Indonesia yang jelas, analitis, dan terstruktur. Untuk pertanyaan faktual atau terkini, gunakan Google Search grounding yang tersedia. Bedakan fakta, dugaan, dan ketidakpastian. Sertakan tanggal jika relevan. Jangan mengarang sumber. Buat jawaban dengan ringkasan, penjelasan, dan poin penting bila cocok."
            }]
          },
          contents: [{ role: "user", parts: [{ text: question }] }],
          tools: [{ google_search: {} }],
          generationConfig: { temperature: 0.35, maxOutputTokens: 1800 }
        })
      }
    );

    const data = await response.json();
    if (!response.ok) {
      const message = data?.error?.message || "Gemini API gagal memproses permintaan.";
      const status = response.status === 429 ? 429 : 502;
      return res.status(status).json({ error: message.slice(0, 350) });
    }

    const answer = (data.candidates?.[0]?.content?.parts || [])
      .map(part => part.text || "")
      .filter(Boolean)
      .join("\n")
      .trim();

    const grounding = data.candidates?.[0]?.groundingMetadata;
    const sources = (grounding?.groundingChunks || [])
      .map(chunk => chunk.web)
      .filter(web => web?.uri && web?.title)
      .map(web => ({ title: web.title, url: web.uri }))
      .filter((item, index, all) => all.findIndex(other => other.url === item.url) === index)
      .slice(0, 8);

    if (!answer) return res.status(502).json({ error: "Gemini tidak mengembalikan jawaban teks. Coba pertanyaan lain." });
    return res.status(200).json({ answer, sources });
  } catch (error) {
    return res.status(500).json({ error: "Tidak dapat menghubungi Gemini saat ini. Periksa koneksi dan konfigurasi backend." });
  }
}
