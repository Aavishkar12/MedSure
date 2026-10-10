package com.powerbank.medsure.ui.patient

import android.Manifest
import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Location
import android.net.Uri
import android.util.Log
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.android.libraries.places.api.Places
import com.google.android.libraries.places.api.model.CircularBounds
import com.google.android.libraries.places.api.net.PlacesClient
import com.google.android.libraries.places.api.net.SearchNearbyRequest
import com.google.maps.android.compose.*
import com.powerbank.medsure.state.MedSureViewModel
import com.powerbank.medsure.state.Place
import com.powerbank.medsure.ui.components.*
import com.powerbank.medsure.ui.theme.Ms
import kotlinx.coroutines.tasks.await
import com.google.android.libraries.places.api.model.Place as GmsPlace

private const val SEARCH_RADIUS_M = 5000.0

/** The Maps key from local.properties (maps.apiKey), or "" when the build has none. */
private fun mapsKey(context: Context): String = runCatching {
    context.packageManager.getApplicationInfo(context.packageName, PackageManager.GET_META_DATA)
        .metaData?.getString("com.google.android.geo.API_KEY").orEmpty()
}.getOrDefault("").trim()

/**
 * Nearby hospitals, clinics and pharmacies on a map, with directions.
 * Without a Maps key (or location) it shows the list only: it must never crash the Help tab.
 */
@SuppressLint("MissingPermission")
@Composable
fun NearbyCareScreen(vm: MedSureViewModel) {
    val context = LocalContext.current
    val t = vm.tx
    val key = remember { mapsKey(context) }
    var hasLocationPermission by remember {
        mutableStateOf(ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED)
    }
    val permissionLauncher = rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { hasLocationPermission = it }

    // Places.initialize throws on an empty key; that used to crash the app as soon as Help opened.
    val placesClient: PlacesClient? = remember(key) {
        if (key.isEmpty()) null else runCatching {
            if (!Places.isInitialized()) Places.initializeWithNewPlacesApiEnabled(context.applicationContext, key)
            Places.createClient(context)
        }.onFailure { Log.w("MedSure", "Places unavailable", it) }.getOrNull()
    }

    var userLocation by remember { mutableStateOf<LatLng?>(null) }
    var searching by remember { mutableStateOf(false) }
    val cameraPositionState = rememberCameraPositionState()

    LaunchedEffect(hasLocationPermission) {
        if (!hasLocationPermission) return@LaunchedEffect
        val location = runCatching {
            val fused = LocationServices.getFusedLocationProviderClient(context)
            fused.lastLocation.await() ?: fused.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, null).await()
        }.getOrNull() ?: return@LaunchedEffect
        val here = LatLng(location.latitude, location.longitude)
        userLocation = here
        cameraPositionState.position = CameraPosition.fromLatLngZoom(here, 13f)
        if (vm.rawPlaces.isEmpty() && placesClient != null) {
            searching = true
            fetchNearbyPlaces(placesClient, vm, here)
            searching = false
        }
    }

    val filters = listOf("all" to t["fAll"], "hosp" to t["fHosp"], "clinic" to t["fClinic"], "pharm" to t["fPharm"])
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (!hasLocationPermission) {
            MsCard(bg = Ms.FlagBg, border = Ms.FlagBorder, gap = 6.dp) {
                T("Location needed", 18, 700, Ms.Brown)
                T("Allow location to see hospitals and pharmacies near you.", 15, 400, Ms.Brown, lh = 1.5f)
                MsButton("Allow location", BtnKind.Danger) { permissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION) }
            }
        } else if (placesClient != null) {
            Box(Modifier.fillMaxWidth().height(250.dp).clip(RoundedCornerShape(22.dp)).background(Ms.Blister)) {
                val here = userLocation
                if (here == null) {
                    CircularProgressIndicator(Modifier.align(Alignment.Center))
                } else {
                    GoogleMap(
                        modifier = Modifier.fillMaxSize(),
                        cameraPositionState = cameraPositionState,
                        properties = MapProperties(isMyLocationEnabled = true),
                    ) {
                        vm.places.filter { it.lat != 0.0 || it.lng != 0.0 }.forEach { place ->
                            Marker(state = MarkerState(position = LatLng(place.lat, place.lng)), title = place.name, snippet = place.dist)
                        }
                    }
                }
            }
        }

        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            filters.forEach { (id, label) -> Chip(label, vm.filter == id) { vm.filter = id } }
        }
        if (searching) T("Finding care near you…", 14, 400, Ms.Muted)
        if (!searching && vm.places.isEmpty()) {
            EmptyNote(if (placesClient == null) t["noPlacesKey"] else t["noPlaces"])
            MsButton(t["findHosp"], BtnKind.Mari, Modifier.fillMaxWidth(), height = 44.dp) {
                openDirections(context, Place("", "hosp", "hospital near me", "", "", "", ""))
            }
        }

        vm.places.forEach { p ->
            MsCard(border = if (vm.chosen == p.id) Ms.Ink else Ms.Line, gap = 12.dp) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Column(Modifier.weight(1f)) {
                        T(p.name, 17, 700)
                        T(p.meta, 14, 400, Ms.Muted)
                    }
                    if (p.dist.isNotEmpty()) D(p.dist, 20)
                }
                if (p.open.isNotEmpty() || p.badge.isNotEmpty()) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (p.open.isNotEmpty()) T(p.open, 13, 700, Ms.GreenFg, Modifier.clip(RoundedCornerShape(999.dp)).background(Ms.GreenBg).padding(horizontal = 10.dp, vertical = 4.dp))
                    if (p.badge.isNotEmpty()) T(p.badge, 13, 700, Ms.Paper, Modifier.clip(RoundedCornerShape(999.dp)).background(Ms.Ink).padding(horizontal = 10.dp, vertical = 4.dp))
                }
                MsButton("Get directions", BtnKind.Mari, Modifier.fillMaxWidth(), height = 44.dp) {
                    vm.chosen = p.id
                    openDirections(context, p)
                }
            }
        }
    }
}

/**
 * Opens Google Maps in its own task. Coming back to MedSure returns to this screen: the app's state
 * is saved when it goes to the background, so it is restored even if Android stopped the app meanwhile.
 */
private fun openDirections(context: Context, p: Place) {
    val known = p.lat != 0.0 || p.lng != 0.0
    val uri = if (known) {
        Uri.parse("https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lng}")
    } else {
        // The hospital from the discharge papers has a name but no coordinates: let Maps find it.
        Uri.parse("https://www.google.com/maps/search/?api=1&query=" + Uri.encode(p.name))
    }
    val intent = Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    try {
        context.startActivity(Intent(intent).setPackage("com.google.android.apps.maps"))
    } catch (_: ActivityNotFoundException) {
        runCatching { context.startActivity(intent) } // a browser, when Google Maps is not installed
    }
}

/** Hospitals, clinics and pharmacies within 5 km, nearest first. Leaves the list as it was if the search fails. */
private suspend fun fetchNearbyPlaces(placesClient: PlacesClient, vm: MedSureViewModel, here: LatLng) {
    try {
        val fields = listOf(GmsPlace.Field.ID, GmsPlace.Field.NAME, GmsPlace.Field.TYPES, GmsPlace.Field.LAT_LNG, GmsPlace.Field.ADDRESS)
        val request = SearchNearbyRequest.builder(CircularBounds.newInstance(here, SEARCH_RADIUS_M), fields)
            .setIncludedTypes(listOf("hospital", "pharmacy", "doctor"))
            .setMaxResultCount(20)
            .setRankPreference(SearchNearbyRequest.RankPreference.DISTANCE)
            .build()
        val found = placesClient.searchNearby(request).await().places.mapNotNull { place ->
            val types = place.placeTypes.orEmpty()
            val type = when {
                "hospital" in types -> "hosp"
                "pharmacy" in types || "drugstore" in types -> "pharm"
                "doctor" in types -> "clinic"
                else -> return@mapNotNull null
            }
            val at = place.latLng ?: return@mapNotNull null
            val meters = FloatArray(1).also { Location.distanceBetween(here.latitude, here.longitude, at.latitude, at.longitude, it) }[0]
            Place(
                id = place.id ?: return@mapNotNull null,
                type = type,
                name = place.name ?: "Healthcare facility",
                meta = place.address.orEmpty(),
                dist = if (meters < 1000) "${meters.toInt()} m" else String.format(java.util.Locale.US, "%.1f km", meters / 1000),
                open = "",
                badge = "",
                lat = at.latitude,
                lng = at.longitude,
            )
        }
        if (found.isNotEmpty()) {
            vm.rawPlaces.clear()
            vm.rawPlaces.addAll(found)
        }
    } catch (e: Exception) {
        Log.w("MedSure", "Nearby search failed", e)
    }
}
