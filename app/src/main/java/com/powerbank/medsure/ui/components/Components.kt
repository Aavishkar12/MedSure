package com.powerbank.medsure.ui.components

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.animateDpAsState
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsFocusedAsState
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.scale
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.powerbank.medsure.ui.theme.Body
import com.powerbank.medsure.ui.theme.Display
import com.powerbank.medsure.ui.theme.Ms

// ---------- Text ----------

/** Body text in Figtree. `lh` is the CSS line-height multiplier. */
@Composable
fun T(
    text: String,
    size: Int = 15,
    weight: Int = 400,
    color: Color = Ms.Ink,
    modifier: Modifier = Modifier,
    lh: Float? = null,
    align: TextAlign? = null,
    spacing: Float = 0f,
    family: FontFamily = Body,
) {
    Text(
        text = text,
        modifier = modifier,
        color = color,
        textAlign = align,
        style = TextStyle(
            fontFamily = family,
            fontSize = size.sp,
            fontWeight = FontWeight(weight),
            lineHeight = if (lh != null) (size * lh).sp else (size * 1.3f).sp,
            letterSpacing = spacing.em,
        ),
    )
}

/** Display text in Bricolage Grotesque, tight tracking like the prototype's `.d` class. */
@Composable
fun D(
    text: String,
    size: Int,
    weight: Int = 800,
    color: Color = Ms.Ink,
    modifier: Modifier = Modifier,
    lh: Float = 1.1f,
) = T(text, size, weight, color, modifier, lh, spacing = -0.02f, family = Display)

/** Small uppercase section label. */
@Composable
fun Caps(text: String, color: Color = Ms.Muted, size: Int = 13, modifier: Modifier = Modifier) =
    T(text, size, 800, color, modifier, spacing = 0.08f)

@Composable
fun Ico(icon: ImageVector, tint: Color, size: Dp = 22.dp, modifier: Modifier = Modifier) =
    Icon(icon, contentDescription = null, tint = tint, modifier = modifier.size(size))

// ---------- Modifiers ----------

/** Shrinks slightly while pressed, like the prototype's :active transform. */
fun Modifier.pressable(
    enabled: Boolean = true,
    pressedScale: Float = 0.97f,
    onClick: () -> Unit,
): Modifier = composed {
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val s by animateFloatAsState(if (pressed && enabled) pressedScale else 1f, label = "press")
    this
        .scale(s)
        .clickable(interactionSource = source, indication = null, enabled = enabled, role = Role.Button, onClick = onClick)
}

/** Dashed rounded border (the prototype's `border: … dashed`). */
fun Modifier.dashedBorder(color: Color, width: Dp, radius: Dp, dash: Dp = 6.dp, gap: Dp = 4.dp) = drawBehind {
    val w = width.toPx()
    drawRoundRect(
        color = color,
        topLeft = androidx.compose.ui.geometry.Offset(w / 2, w / 2),
        size = androidx.compose.ui.geometry.Size(size.width - w, size.height - w),
        cornerRadius = CornerRadius(radius.toPx()),
        style = Stroke(width = w, pathEffect = PathEffect.dashPathEffect(floatArrayOf(dash.toPx(), gap.toPx()))),
    )
}

// ---------- Containers ----------

/** White card: 22 radius, 1px #E6E0D8 border, 18 padding. */
@Composable
fun MsCard(
    modifier: Modifier = Modifier,
    bg: Color = Ms.White,
    border: Color? = Ms.Line,
    borderWidth: Dp = 1.dp,
    radius: Dp = 22.dp,
    padding: PaddingValues = PaddingValues(18.dp),
    gap: Dp = 0.dp,
    onClick: (() -> Unit)? = null,
    content: @Composable ColumnScope.() -> Unit,
) {
    val shape = RoundedCornerShape(radius)
    var m = modifier.clip(shape).background(bg, shape)
    if (border != null) m = m.border(borderWidth, border, shape)
    if (onClick != null) m = m.pressable(pressedScale = 0.98f, onClick = onClick)
    Column(m.padding(padding), verticalArrangement = Arrangement.spacedBy(gap), content = content)
}

/** Round "tick" badge used for avatars and status dots. */
@Composable
fun Tick(size: Dp, bg: Color, modifier: Modifier = Modifier, shape: Shape = CircleShape, content: @Composable BoxScope.() -> Unit) {
    Box(modifier.size(size).clip(shape).background(bg), contentAlignment = Alignment.Center, content = content)
}

// ---------- Buttons ----------

enum class BtnKind { Primary, Mari, Ghost, Danger, Light }

@Composable
fun MsButton(
    text: String,
    kind: BtnKind,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    icon: ImageVector? = null,
    height: Dp = 50.dp,
    fontSize: Int = 15,
    hPad: Dp = 18.dp,
    borderColor: Color? = null,
    textColor: Color? = null,
    onClick: () -> Unit,
) {
    val shape = RoundedCornerShape(15.dp)
    val (bg, fg, border) = when {
        !enabled -> Triple(Color(0xFFD9D3CA), Ms.Muted2, null)
        kind == BtnKind.Primary -> Triple(Ms.Teal, Color.White, null)
        kind == BtnKind.Mari -> Triple(Ms.Marigold, Ms.Ink, null)
        kind == BtnKind.Ghost -> Triple(Color.Transparent, textColor ?: Ms.Ink, BorderStroke(1.5.dp, borderColor ?: Ms.Ink))
        kind == BtnKind.Danger -> Triple(Ms.Red, Color.White, null)
        else -> Triple(Ms.White, Ms.Ink, BorderStroke(1.dp, Ms.Line))
    }
    var m = modifier.heightIn(min = height).clip(shape).background(bg, shape)
    if (border != null) m = m.border(border, shape)
    Row(
        m.pressable(enabled = enabled, onClick = onClick).padding(horizontal = hPad, vertical = 6.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp, Alignment.CenterHorizontally),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        if (icon != null) Ico(icon, fg, 18.dp)
        T(text, fontSize, 700, fg, align = TextAlign.Center)
    }
}

/** Round 46dp icon button (back, settings, close). */
@Composable
fun IconBtn(icon: ImageVector, label: String, onClick: () -> Unit) {
    Box(
        Modifier.size(46.dp).clip(CircleShape).background(Ms.White).border(1.dp, Ms.Line, CircleShape)
            .pressable(onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { Icon(icon, contentDescription = label, tint = Ms.Ink, modifier = Modifier.size(22.dp)) }
}

/** Pill chip. Selected = ink fill. */
@Composable
fun Chip(label: String, selected: Boolean, modifier: Modifier = Modifier, leading: ImageVector? = null, onClick: () -> Unit) {
    val shape = RoundedCornerShape(999.dp)
    Row(
        modifier.heightIn(min = 42.dp).clip(shape)
            .background(if (selected) Ms.Ink else Ms.White)
            .border(1.5.dp, if (selected) Ms.Ink else Ms.Line2, shape)
            .pressable(onClick = onClick)
            .padding(horizontal = 14.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(6.dp),
    ) {
        val fg = if (selected) Ms.Paper else Ms.Text3
        if (leading != null) Ico(leading, fg, 18.dp)
        T(label, 14, 600, fg)
    }
}

/** 54x32 toggle switch. */
@Composable
fun MsSwitch(on: Boolean, label: String, onToggle: () -> Unit) {
    val bg by animateColorAsState(if (on) Ms.Teal else Ms.SwitchOff, label = "sw")
    val x by animateDpAsState(if (on) 26.dp else 4.dp, label = "knob")
    Box(
        Modifier.size(54.dp, 32.dp).clip(RoundedCornerShape(999.dp)).background(bg)
            .clickable(role = Role.Switch, onClickLabel = label, onClick = onToggle),
    ) {
        Box(Modifier.offset(x = x, y = 4.dp).size(24.dp).clip(CircleShape).background(Color.White))
    }
}

/** Labelled text input with the prototype's focus ring. */
@Composable
fun Field(
    label: String?,
    value: String,
    onChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    keyboard: KeyboardType = KeyboardType.Text,
    singleLine: Boolean = true,
    minHeight: Dp = 54.dp,
    otp: Boolean = false,
    labelContent: (@Composable () -> Unit)? = null,
) {
    Column(modifier, verticalArrangement = Arrangement.spacedBy(6.dp)) {
        if (labelContent != null) labelContent() else if (label != null) T(label, 14, 700, Ms.Text3)
        val source = remember { MutableInteractionSource() }
        val focused by source.collectIsFocusedAsState()
        val shape = RoundedCornerShape(14.dp)
        val style = TextStyle(
            fontFamily = Body,
            fontSize = if (otp) 24.sp else 17.sp,
            fontWeight = if (otp) FontWeight.Bold else FontWeight.Normal,
            letterSpacing = if (otp) 0.6.em else 0.em,
            textAlign = if (otp) TextAlign.Center else TextAlign.Start,
            color = Ms.Ink,
            lineHeight = if (singleLine) 22.sp else (17 * 1.5f).sp,
        )
        BasicTextField(
            value = value,
            onValueChange = onChange,
            singleLine = singleLine,
            textStyle = style,
            cursorBrush = SolidColor(Ms.Teal),
            interactionSource = source,
            keyboardOptions = KeyboardOptions(keyboardType = keyboard),
            modifier = Modifier.fillMaxWidth(),
            decorationBox = { inner ->
                Box(
                    Modifier.fillMaxWidth().heightIn(min = minHeight).clip(shape).background(Ms.White)
                        .border(1.5.dp, if (focused) Ms.Teal else Ms.Line2, shape)
                        .padding(horizontal = 16.dp, vertical = if (singleLine) 0.dp else 14.dp),
                    contentAlignment = if (singleLine) Alignment.CenterStart else Alignment.TopStart,
                ) {
                    if (value.isEmpty()) {
                        T(placeholder, if (otp) 24 else 17, 400, Ms.Pale, Modifier.fillMaxWidth(), align = if (otp) TextAlign.Center else null)
                    }
                    inner()
                }
            },
        )
    }
}

/** Dot separator used in the header lines. */
@Composable
fun Dot(color: Color = Ms.Pale) = Box(Modifier.size(4.dp).clip(CircleShape).background(color))

/** Horizontal rule. */
@Composable
fun Rule(color: Color = Ms.Line, modifier: Modifier = Modifier) =
    Box(modifier.fillMaxWidth().height(1.dp).background(color))
