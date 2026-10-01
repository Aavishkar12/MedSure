package com.powerbank.medsure.ui.components

import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.unit.dp
import androidx.compose.ui.graphics.Color

/**
 * The same 24x24 stroke icons the prototype draws inline (Lucide-style, 2px stroke,
 * round caps). Tint them with Icon(tint = …).
 */
object LineIcons {
    private fun circle(cx: Float, cy: Float, r: Float) =
        "M${cx - r} $cy A$r $r 0 1 0 ${cx + r} $cy A$r $r 0 1 0 ${cx - r} $cy Z"

    private fun icon(name: String, vararg paths: String): ImageVector {
        val b = ImageVector.Builder(
            name = name, defaultWidth = 24.dp, defaultHeight = 24.dp,
            viewportWidth = 24f, viewportHeight = 24f,
        )
        paths.forEach { d ->
            b.addPath(
                pathData = addPathNodes(d),
                fill = null,
                stroke = SolidColor(Color.Black),
                strokeLineWidth = 2f,
                strokeLineCap = StrokeCap.Round,
                strokeLineJoin = StrokeJoin.Round,
            )
        }
        return b.build()
    }

    val Check by lazy { icon("check", "M20 6 L9 17 L4 12") }
    val ChevronRight by lazy { icon("chev-r", "M9 18 L15 12 L9 6") }
    val ChevronLeft by lazy { icon("chev-l", "M15 18 L9 12 L15 6") }
    val Close by lazy { icon("x", "M18 6 L6 18", "M6 6 L18 18") }
    val Pill by lazy {
        icon("pill", "M10.5 20.5 L3.5 13.5 A5 5 0 0 1 10.5 6.5 L17.5 13.5 A5 5 0 0 1 10.5 20.5 Z", "M8.5 8.5 L15.5 15.5")
    }
    val FileText by lazy {
        icon("file", "M14 2 H6 A2 2 0 0 0 4 4 V20 A2 2 0 0 0 6 22 H18 A2 2 0 0 0 20 20 V8 Z", "M14 2 L14 8 L20 8", "M8 13 L16 13")
    }
    val File by lazy {
        icon("file2", "M14 2 H6 A2 2 0 0 0 4 4 V20 A2 2 0 0 0 6 22 H18 A2 2 0 0 0 20 20 V8 Z", "M14 2 L14 8 L20 8")
    }
    val Activity by lazy { icon("activity", "M22 12 L18 12 L15 21 L9 3 L6 12 L2 12") }
    val MapPin by lazy {
        icon("pin", "M21 10 C21 17 12 23 12 23 C12 23 3 17 3 10 A9 9 0 0 1 21 10 Z", circle(12f, 10f, 3f))
    }
    val Home by lazy { icon("home", "M3 10.5 L12 3 L21 10.5 V21 A1 1 0 0 1 20 22 H15 V15 H9 V22 H4 A1 1 0 0 1 3 21 Z") }
    val Receipt by lazy {
        icon(
            "receipt",
            "M4 2 V22 L6 21 L8 22 L10 21 L12 22 L14 21 L16 22 L18 21 L20 22 V2 L18 3 L16 2 L14 3 L12 2 L10 3 L8 2 L6 3 Z",
            "M8 8 L16 8", "M8 12 L16 12",
        )
    }
    val Shield by lazy { icon("shield", "M12 22 C12 22 20 18 20 12 V5 L12 2 L4 5 V12 C4 18 12 22 12 22 Z") }
    val Settings by lazy {
        icon(
            "settings",
            "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z",
            circle(12f, 12f, 3f),
        )
    }
    val Globe by lazy {
        icon(
            "globe", circle(12f, 12f, 10f), "M2 12 L22 12",
            "M12 2 A15.3 15.3 0 0 1 16 12 A15.3 15.3 0 0 1 12 22 A15.3 15.3 0 0 1 8 12 A15.3 15.3 0 0 1 12 2 Z",
        )
    }
    val User by lazy { icon("user", circle(12f, 8f, 4f), "M4 21 V20 A6 6 0 0 1 10 14 H14 A6 6 0 0 1 20 20 V21") }
    val Users by lazy {
        icon(
            "users", "M17 21 V19 A4 4 0 0 0 13 15 H5 A4 4 0 0 0 1 19 V21", circle(9f, 7f, 4f),
            "M23 21 V19 A4 4 0 0 0 20 15.13", "M16 3.13 A4 4 0 0 1 16 10.88",
        )
    }
    val UserPlus by lazy {
        icon(
            "user-plus", "M16 21 V19 A4 4 0 0 0 12 15 H5 A4 4 0 0 0 1 19 V21", circle(8.5f, 7f, 4f),
            "M20 8 L20 14", "M23 11 L17 11",
        )
    }
    val Mic by lazy {
        icon(
            "mic", "M12 2 A3 3 0 0 1 15 5 V11 A3 3 0 0 1 9 11 V5 A3 3 0 0 1 12 2 Z",
            "M19 10 V12 A7 7 0 0 1 5 12 V10", "M12 19 L12 22", "M8 22 L16 22",
        )
    }
    val Volume by lazy {
        icon("volume", "M11 5 L6 9 L2 9 L2 15 L6 15 L11 19 Z", "M15.54 8.46 A5 5 0 0 1 15.54 15.53", "M19.07 4.93 A10 10 0 0 1 19.07 19.07")
    }
    val Alert by lazy {
        icon(
            "alert", "M10.29 3.86 L1.82 18 A2 2 0 0 0 3.53 21 H20.47 A2 2 0 0 0 22.18 18 L13.71 3.86 A2 2 0 0 0 10.29 3.86 Z",
            "M12 9 L12 13", "M12 17 L12.01 17",
        )
    }
    val Exclaim by lazy { icon("exclaim", "M12 7 L12 13", "M12 17 L12.01 17") }
    val Clock by lazy { icon("clock", circle(12f, 12f, 10f), "M12 6 L12 12 L16 14") }
    val Camera by lazy {
        icon("camera", "M23 19 A2 2 0 0 1 21 21 H3 A2 2 0 0 1 1 19 V8 A2 2 0 0 1 3 6 H7 L9 3 H15 L17 6 H21 A2 2 0 0 1 23 8 Z", circle(12f, 13f, 4f))
    }
    val Lock by lazy {
        icon("lock", "M5 11 H19 A2 2 0 0 1 21 13 V20 A2 2 0 0 1 19 22 H5 A2 2 0 0 1 3 20 V13 A2 2 0 0 1 5 11 Z", "M7 11 V7 A5 5 0 0 1 17 7 V11")
    }
    val LogOut by lazy { icon("logout", "M9 21 H5 A2 2 0 0 1 3 19 V5 A2 2 0 0 1 5 3 H9", "M16 17 L21 12 L16 7", "M21 12 L9 12") }
    val Pen by lazy { icon("pen", "M12 20 H21", "M16.5 3.5 A2.12 2.12 0 0 1 19.5 6.5 L7 19 L3 20 L4 16 Z") }
    val Upload by lazy {
        icon("upload", "M21 15 V19 A2 2 0 0 1 19 21 H5 A2 2 0 0 1 3 19 V15", "M17 8 L12 3 L7 8", "M12 3 V15")
    }
    val Paperclip by lazy {
        icon("paperclip", "M21.44 11.05 L12.25 20.24 A6 6 0 0 1 3.76 11.75 L12.95 2.56 A4 4 0 0 1 18.61 8.22 L9.41 17.41 A2 2 0 0 1 6.58 14.58 L15.07 6.1")
    }
}

