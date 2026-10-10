package com.powerbank.medsure.ocr

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.pdf.PdfRenderer
import android.net.Uri
import android.os.ParcelFileDescriptor
import android.util.Log
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.TextRecognizer
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import com.powerbank.medsure.state.UploadedDoc
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import java.io.File

/**
 * Reads the text of scans and photos on the phone with Google ML Kit. Nothing is sent anywhere to be
 * read: the backend only receives the resulting text, stores it, and passes that text to the AI.
 *
 * Pages are marked [Page N], which is how the backend tells the AI where each line came from.
 */
object OnDeviceText {
    /** Pages read from one document. Longer documents are cut off here, like the camera scanner. */
    const val MAX_PAGES = 20
    private const val MIN_USEFUL_CHARS = 40
    private const val PDF_PAGE_LONG_SIDE_PX = 2200 // about 200 dpi for A4, which is what text reading likes
    private const val PDF_SNIFF_BYTES = 8 * 1024 * 1024
    private val IMAGE_EXTENSIONS = listOf(".jpg", ".jpeg", ".png", ".webp", ".bmp", ".heic", ".heif")

    /** Text of page pictures, e.g. the pages of a camera scan. Null when nothing useful could be read. */
    suspend fun readPages(context: Context, pages: List<Uri>): String? {
        if (pages.isEmpty()) return null
        return withRecognizer { recognizer ->
            pages.take(MAX_PAGES).mapIndexedNotNull { i, uri ->
                val text = runCatching {
                    recognizer.process(withContext(Dispatchers.IO) { InputImage.fromFilePath(context, uri) }).await().text.trim()
                }.onFailure { Log.w("MedSure", "Could not read page ${i + 1}", it) }.getOrNull()
                marked(i + 1, text)
            }
        }
    }

    /**
     * Text of a photo or PDF the user picked from their files. Null when there is nothing to read
     * here: a typed PDF (the backend takes its text straight from the file) or a picture without text.
     */
    suspend fun readPicked(context: Context, doc: UploadedDoc): String? = try {
        val name = doc.name.lowercase()
        when {
            doc.isPdf -> if (pdfHasTypedText(context, doc.uri)) null else readPdf(context, doc.uri)
            doc.mimeType.startsWith("image/") || IMAGE_EXTENSIONS.any(name::endsWith) -> readPages(context, listOf(doc.uri))
            else -> null
        }
    } catch (e: Exception) {
        Log.w("MedSure", "Could not read ${doc.name} on the phone", e)
        null
    }

    /**
     * A PDF made of typed text carries fonts; one made of page pictures (a scan) does not. This is only
     * a shortcut to skip needless work: the backend prefers a PDF's own text whenever it has one.
     */
    private suspend fun pdfHasTypedText(context: Context, uri: Uri): Boolean = withContext(Dispatchers.IO) {
        context.contentResolver.openInputStream(uri)?.use { input ->
            val buffer = ByteArray(64 * 1024)
            var seen = 0
            var tail = ""
            while (seen < PDF_SNIFF_BYTES) {
                val n = input.read(buffer)
                if (n <= 0) break
                val chunk = tail + String(buffer, 0, n, Charsets.ISO_8859_1)
                if ("/Font" in chunk) return@use true
                tail = chunk.takeLast(8) // the marker may straddle two reads
                seen += n
            }
            false
        } ?: false
    }

    /** Draws each page of a scanned PDF and reads it. */
    private suspend fun readPdf(context: Context, uri: Uri): String? {
        // PdfRenderer needs a real file it can seek in; a picked document may only be a stream.
        val copy = withContext(Dispatchers.IO) {
            File.createTempFile("read", ".pdf", context.cacheDir).also { file ->
                context.contentResolver.openInputStream(uri)!!.use { input -> file.outputStream().use { input.copyTo(it) } }
            }
        }
        try {
            return withRecognizer { recognizer ->
                withContext(Dispatchers.IO) { PdfRenderer(ParcelFileDescriptor.open(copy, ParcelFileDescriptor.MODE_READ_ONLY)) }.use { pdf ->
                    (0 until minOf(pdf.pageCount, MAX_PAGES)).mapNotNull { i ->
                        val bitmap = withContext(Dispatchers.Default) {
                            pdf.openPage(i).use { page ->
                                val scale = PDF_PAGE_LONG_SIDE_PX.toFloat() / maxOf(page.width, page.height)
                                Bitmap.createBitmap((page.width * scale).toInt(), (page.height * scale).toInt(), Bitmap.Config.ARGB_8888).also {
                                    it.eraseColor(Color.WHITE) // pages are transparent where nothing is drawn
                                    page.render(it, null, null, PdfRenderer.Page.RENDER_MODE_FOR_PRINT)
                                }
                            }
                        }
                        try {
                            marked(i + 1, recognizer.process(InputImage.fromBitmap(bitmap, 0)).await().text.trim())
                        } finally {
                            bitmap.recycle()
                        }
                    }
                }
            }
        } finally {
            copy.delete()
        }
    }

    private fun marked(page: Int, text: String?): String? = text?.takeIf { it.isNotEmpty() }?.let { "[Page $page]\n$it" }

    private suspend fun withRecognizer(read: suspend (TextRecognizer) -> List<String>): String? {
        val recognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
        return try {
            read(recognizer).joinToString("\n\n").takeIf { it.length >= MIN_USEFUL_CHARS }
        } finally {
            recognizer.close()
        }
    }
}
