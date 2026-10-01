package com.powerbank.medsure.ui.patient

import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.*
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.powerbank.medsure.state.MedSureViewModel
import com.powerbank.medsure.ui.components.D
import com.powerbank.medsure.ui.components.Ico
import com.powerbank.medsure.ui.components.LineIcons
import com.powerbank.medsure.ui.components.T
import com.powerbank.medsure.ui.theme.Ms
import kotlinx.coroutines.delay

/**
 * Premium loading & preparation screen.
 * Displays animated blister strip morphing into checkmarks,
 * sequential checklist steps, and synchronized gradient progress bar.
 */
@Composable
fun ProcessingScreen(vm: MedSureViewModel) {
    // Disable system back gesture/button on this screen
    BackHandler(enabled = true) {
        // No-op: back disabled while processing
    }

    val context = LocalContext.current
    val reduceMotion = remember {
        try {
            Settings.Global.getFloat(
                context.contentResolver,
                Settings.Global.ANIMATOR_DURATION_SCALE,
                1.0f,
            ) == 0f
        } catch (_: Exception) {
            false
        }
    }

    // Processing animation states
    var completedPills by remember { mutableIntStateOf(0) }
    var activeStep by remember { mutableIntStateOf(0) }
    var completedSteps by remember { mutableIntStateOf(0) }
    var targetProgress by remember { mutableFloatStateOf(0.08f) }

    // Simulated for demo. No real processing happens.
    LaunchedEffect(Unit) {
        // Step 1: Securing your documents (0ms - 1100ms)
        activeStep = 0
        targetProgress = 0.28f
        delay(650)
        completedPills = 1
        delay(450)
        completedSteps = 1

        // Step 2: Reading your discharge papers (1100ms - 2200ms)
        activeStep = 1
        targetProgress = 0.52f
        delay(400)
        completedPills = 2
        delay(700)
        completedSteps = 2

        // Step 3: Setting up your medicine reminders (2200ms - 3300ms)
        activeStep = 2
        targetProgress = 0.76f
        delay(300)
        completedPills = 3
        delay(800)
        completedSteps = 3

        // Step 4: Preparing your home screen (3300ms - 4400ms)
        activeStep = 3
        targetProgress = 1.0f
        delay(250)
        completedPills = 4
        delay(850)
        completedSteps = 4
        completedPills = 5

        // Hold for 400ms upon final completion, then navigate to Patient Home
        delay(400)
        vm.completeProcessing()
    }

    val progress by animateFloatAsState(
        targetValue = targetProgress,
        animationSpec = if (reduceMotion) snap() else tween(durationMillis = 800, easing = FastOutSlowInEasing),
        label = "sync_progress",
    )

    Column(
        Modifier.fillMaxSize()
            .padding(horizontal = 24.dp, vertical = 32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.SpaceBetween,
    ) {
        // Top section: Row of 5 blister pills morphing to checkmarks
        Column(
            Modifier.fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(24.dp),
        ) {
            Spacer(Modifier.height(8.dp))

            // Reused 5-pill blister strip from welcome screen header
            Row(
                Modifier.fillMaxWidth().clip(RoundedCornerShape(28.dp)).background(Ms.Blister).padding(18.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                for (i in 0 until 5) {
                    AnimatedBlisterPill(
                        isCheck = i < completedPills,
                        reduceMotion = reduceMotion,
                        modifier = Modifier.weight(1f),
                    )
                }
            }

            // Headline & hardcoded Lakshmi greeting subtext
            Column(
                Modifier.fillMaxWidth().padding(top = 8.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                D("Setting things up for you", 30, lh = 1.15f)
                T("Lakshmi, this takes just a moment.", 16, 400, Ms.Text3)
            }
        }

        // Center section: Vertical checklist of 4 steps
        Column(
            Modifier.fillMaxWidth().padding(vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            val stepTitles = listOf(
                "Securing your documents",
                "Reading your discharge papers",
                "Setting up your medicine reminders",
                "Preparing your home screen",
            )

            stepTitles.forEachIndexed { index, title ->
                val isDone = completedSteps > index
                val isActive = activeStep == index && !isDone
                ChecklistStepRow(
                    title = title,
                    isDone = isDone,
                    isActive = isActive,
                    reduceMotion = reduceMotion,
                )
            }
        }

        // Bottom section: Horizontal gradient progress bar
        Column(
            Modifier.fillMaxWidth().padding(bottom = 16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Box(
                Modifier.fillMaxWidth().height(8.dp).clip(RoundedCornerShape(999.dp)).background(Ms.Blister)
            ) {
                Box(
                    Modifier.fillMaxHeight().fillMaxWidth(progress)
                        .clip(RoundedCornerShape(999.dp))
                        .background(Brush.horizontalGradient(listOf(Ms.Marigold, Ms.Teal)))
                )
            }
        }
    }
}

/**
 * Single blister pill from landing screen header that smoothly flips
 * into a teal checkmark.
 */
@Composable
private fun AnimatedBlisterPill(
    isCheck: Boolean,
    reduceMotion: Boolean,
    modifier: Modifier = Modifier,
) {
    val rotation by animateFloatAsState(
        targetValue = if (isCheck && !reduceMotion) 180f else 0f,
        animationSpec = tween(400, easing = FastOutSlowInEasing),
        label = "pill_flip",
    )

    val bgColor by animateColorAsState(
        targetValue = if (isCheck) Ms.Taken else Ms.White,
        animationSpec = tween(300),
        label = "pill_bg",
    )

    Box(
        modifier.aspectRatio(1f)
            .graphicsLayer {
                rotationY = rotation
                cameraDistance = 12f * density
            }
            .drawBehind {
                drawCircle(
                    Ms.BubbleShadow,
                    radius = size.minDimension / 2,
                    center = center.copy(y = center.y + 3.dp.toPx()),
                )
            }
            .clip(CircleShape)
            .background(bgColor),
        contentAlignment = Alignment.Center,
    ) {
        if (rotation >= 90f || (reduceMotion && isCheck)) {
            // Flipped side: teal checkmark
            Box(Modifier.graphicsLayer { if (!reduceMotion) scaleX = -1f }) {
                Ico(LineIcons.Check, Ms.Teal, 22.dp)
            }
        } else {
            // Front side: amber pill
            Box(
                Modifier.fillMaxWidth(0.6f).fillMaxHeight(0.28f).rotate(-32f)
                    .clip(RoundedCornerShape(999.dp)).background(Ms.Marigold)
            )
        }
    }
}

/**
 * Checklist row representing a stage in the setup process.
 * Shows muted grey dot -> gentle amber pulse -> teal check with pop animation.
 */
@Composable
private fun ChecklistStepRow(
    title: String,
    isDone: Boolean,
    isActive: Boolean,
    reduceMotion: Boolean,
) {
    val inf = rememberInfiniteTransition(label = "pulse")
    val pulseScale by inf.animateFloat(
        initialValue = 1f,
        targetValue = 1.35f,
        animationSpec = infiniteRepeatable(
            animation = tween(900, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "pulse_scale",
    )
    val pulseAlpha by inf.animateFloat(
        initialValue = 0.5f,
        targetValue = 0f,
        animationSpec = infiniteRepeatable(
            animation = tween(900, easing = FastOutSlowInEasing),
            repeatMode = RepeatMode.Reverse,
        ),
        label = "pulse_alpha",
    )

    Row(
        Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        // Icon / Indicator container (32x32dp for alignment)
        Box(Modifier.size(32.dp), contentAlignment = Alignment.Center) {
            when {
                isDone -> {
                    // Teal checkmark badge
                    Box(
                        Modifier.size(28.dp).clip(CircleShape).background(Ms.Teal),
                        contentAlignment = Alignment.Center,
                    ) {
                        Ico(LineIcons.Check, Color.White, 16.dp)
                    }
                }
                isActive -> {
                    // Amber pulse ring
                    if (!reduceMotion) {
                        Box(
                            Modifier.size(24.dp).scale(pulseScale).alpha(pulseAlpha)
                                .clip(CircleShape).background(Ms.Marigold)
                        )
                    }
                    Box(
                        Modifier.size(20.dp).clip(CircleShape).background(Ms.Marigold)
                            .border(2.dp, Ms.Paper, CircleShape),
                    )
                }
                else -> {
                    // Muted grey dot
                    Box(
                        Modifier.size(10.dp).clip(CircleShape).background(Ms.Line2)
                    )
                }
            }
        }

        // Step title
        val textWeight = if (isActive || isDone) 700 else 400
        val textColor = when {
            isDone -> Ms.Ink
            isActive -> Ms.Ink
            else -> Ms.Muted
        }
        T(
            text = title,
            size = 16,
            weight = textWeight,
            color = textColor,
            modifier = Modifier.weight(1f),
        )
    }
}
