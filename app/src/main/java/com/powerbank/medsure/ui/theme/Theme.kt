package com.powerbank.medsure.ui.theme

import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.ExperimentalTextApi
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import com.powerbank.medsure.R

/** Tamarind palette — every value is copied from the web prototype. */
object Ms {
    val Ink = Color(0xFF221C18)
    val Paper = Color(0xFFFAFAF7)
    val Outside = Color(0xFFE7E2DA)
    val White = Color(0xFFFFFFFF)
    val Muted = Color(0xFF5E554E)
    val Muted2 = Color(0xFF6B625B)
    val Text3 = Color(0xFF3C342E)
    val Line = Color(0xFFE6E0D8)
    val Line2 = Color(0xFFD9D3CA)
    val Line3 = Color(0xFFE0D9CF)
    val Handle = Color(0xFFCFC8BE)
    val Pale = Color(0xFFB9B0A5)
    val SwitchOff = Color(0xFFC9C1B6)
    val Marigold = Color(0xFFF4A62A)
    val Teal = Color(0xFF0E5A52)
    val Red = Color(0xFF9E1C12)
    val Blister = Color(0xFFECE8E2)
    val BlisterEdge = Color(0xFFDED8CF)
    val BubbleShadow = Color(0xFFD3CCC2)
    val Taken = Color(0xFFDCD6CD)
    val GreenBg = Color(0xFFDDEFE3)
    val GreenFg = Color(0xFF17462A)
    val GreenDot = Color(0xFF2F7D4F)
    val AmberBg = Color(0xFFFCE3B8)
    val AmberFg = Color(0xFF5A3300)
    val AmberDot = Color(0xFFE39A1F)
    val AmberText = Color(0xFF8A5200)
    val AmberDark = Color(0xFF6B3D00)
    val Warn = Color(0xFF9A5A00)
    val FlagBg = Color(0xFFFFF4DE)
    val FlagBorder = Color(0xFFC9861A)
    val Brown = Color(0xFF4A2B00)
    val OnDark = Color(0xFFDCD6CD)
    val PlusSel = Color(0xFF3A2E22)
    val PlusLine = Color(0xFF4A403A)
    val PlusBadge = Color(0xFF3A322C)
}

@OptIn(ExperimentalTextApi::class)
private fun figtree(w: Int) = Font(
    R.font.figtree,
    weight = FontWeight(w),
    variationSettings = FontVariation.Settings(FontVariation.weight(w)),
)

@OptIn(ExperimentalTextApi::class)
private fun bricolage(w: Int) = Font(
    R.font.bricolage,
    weight = FontWeight(w),
    variationSettings = FontVariation.Settings(FontVariation.weight(w)),
)

/** Body text: Figtree. Tamil and Devanagari fall back to the system Noto fonts. */
val Body = FontFamily(figtree(400), figtree(500), figtree(600), figtree(700), figtree(800))

/** Display text: Bricolage Grotesque. */
val Display = FontFamily(bricolage(600), bricolage(700), bricolage(800))
