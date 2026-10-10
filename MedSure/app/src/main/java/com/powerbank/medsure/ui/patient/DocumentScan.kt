package com.powerbank.medsure.ui.patient

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.net.Uri
import android.util.Log
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.platform.LocalContext
import com.google.mlkit.vision.documentscanner.GmsDocumentScannerOptions
import com.google.mlkit.vision.documentscanner.GmsDocumentScanning
import com.google.mlkit.vision.documentscanner.GmsDocumentScanningResult
import com.powerbank.medsure.ocr.OnDeviceText
import com.powerbank.medsure.state.UploadedDoc
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}

/**
 * Camera scanning for paper documents. Returns a function that opens Google's document scanner:
 * it finds the page edges, straightens and cleans each page, and lets the user add more pages.
 *
 * The scan comes back as one PDF kept in the app's own storage (so it is still there after a
 * restart), together with the text read from each page on the phone. That text is what the backend
 * stores and sends to the AI: the page pictures themselves are never sent to be read.
 *
 * The scanner runs inside Google Play services, so the app needs no camera permission.
 */
@Composable
fun rememberDocumentScanner(onScanned: (UploadedDoc) -> Unit, onError: (String) -> Unit = {}): () -> Unit {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val scanner = remember {
        GmsDocumentScanning.getClient(
            GmsDocumentScannerOptions.Builder()
                .setScannerMode(GmsDocumentScannerOptions.SCANNER_MODE_FULL)
                .setGalleryImportAllowed(true)
                .setPageLimit(OnDeviceText.MAX_PAGES)
                .setResultFormats(GmsDocumentScannerOptions.RESULT_FORMAT_PDF, GmsDocumentScannerOptions.RESULT_FORMAT_JPEG)
                .build()
        )
    }
    val launcher = rememberLauncherForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) { result ->
        if (result.resultCode != Activity.RESULT_OK) return@rememberLauncherForActivityResult // cancelled
        val scan = GmsDocumentScanningResult.fromActivityResultIntent(result.data)
        val pdf = scan?.pdf
        if (pdf == null) {
            onError("The scan could not be saved. Please try again.")
            return@rememberLauncherForActivityResult
        }
        val app = context.applicationContext
        scope.launch {
            try {
                val pages = scan.pages.orEmpty().map { it.imageUri }
                val doc = withContext(Dispatchers.IO) { saveScan(app, pdf.uri) }
                onScanned(doc.copy(ocrText = OnDeviceText.readPages(app, pages)))
            } catch (e: Exception) {
                Log.w("MedSure", "Saving the scan failed", e)
                onError("The scan could not be saved. Please try again.")
            }
        }
    }
    return {
        val activity = context.findActivity()
        if (activity == null) {
            onError("The camera cannot be opened from here.")
        } else {
            scanner.getStartScanIntent(activity)
                .addOnSuccessListener { launcher.launch(IntentSenderRequest.Builder(it).build()) }
                .addOnFailureListener {
                    Log.w("MedSure", "Document scanner unavailable", it)
                    onError("The scanner is not available on this phone yet. Check that Google Play services is up to date, or upload a file instead.")
                }
        }
    }
}

/** Copies the scanner's PDF out of its temporary folder into files/scans, where it stays until uploaded. */
private fun saveScan(context: Context, source: Uri): UploadedDoc {
    val stamp = SimpleDateFormat("yyyy-MM-dd HH.mm.ss", Locale.US).format(Date())
    val folder = File(context.filesDir, "scans").apply { mkdirs() }
    val file = File(folder, "Scan $stamp.pdf")
    context.contentResolver.openInputStream(source)!!.use { input -> file.outputStream().use { input.copyTo(it) } }
    return UploadedDoc(Uri.fromFile(file), file.name, file.length(), "application/pdf")
}
