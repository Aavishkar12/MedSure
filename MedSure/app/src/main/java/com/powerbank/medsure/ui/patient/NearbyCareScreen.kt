package com.powerbank.medsure.ui.patient

import android.Manifest
import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.location.Geocoder
import android.location.Location
import android.net.Uri
import android.os.Looper
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
import com.google.android.gms.location.LocationCallback
import com.google.android.gms.location.LocationRequest
import com.google.android.gms.location.LocationResult
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import com.google.android.gms.maps.model.BitmapDescriptorFactory
import com.google.android.gms.maps.model.CameraPosition
import com.google.android.gms.maps.model.LatLng
import com.google.android.libraries.places.api.Places
import com.google.android.libraries.places.api.model.CircularBounds
import com.google.android.libraries.places.api.model.RectangularBounds
import com.google.android.libraries.places.api.net.PlacesClient
import com.google.android.libraries.places.api.net.SearchByTextRequest
import com.google.android.libraries.places.api.net.SearchNearbyRequest
import com.google.maps.android.compose.*
import com.powerbank.medsure.state.MedSureViewModel
import com.powerbank.medsure.state.Place
import com.powerbank.medsure.ui.components.*
import com.powerbank.medsure.ui.theme.Ms
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.tasks.await
import kotlinx.coroutines.withContext
import com.google.android.libraries.places.api.model.Place as GmsPlace

/** How far from the phone care is listed. */
private const val RANGE_M = 60_000.0
/** The furthest one "nearby" search may reach (a limit of Google's Places API). */
private const val NEARBY_MAX_M = 50_000.0
/** Places returned per search (the API's maximum). */
private const val PER_SEARCH = 20
/** Search again once the phone has moved this far from where it last searched. */
private const val RESEARCH_AFTER_M = 2_000f

/** One filter chip: the app's type, the Google place types it means, and words for a text search. */
private class Category(val type: String, val placeTypes: List<String>, val query: String)

private val CATEGORIES = listOf(
    Category("hosp", listOf("hospital"), "hospital"),
    Category("pharm", listOf("pharmacy", "drugstore"), "pharmacy medical store"),
    Category("clinic", listOf("doctor"), "clinic dispensary"),
)

private val PLACE_FIELDS = listOf(GmsPlace.Field.ID, GmsPlace.Field.NAME, GmsPlace.Field.LAT_LNG, GmsPlace.Field.ADDRESS)

/** The Maps key from local.properties (maps.apiKey), or "" when the build has none. */
private fun mapsKey(context: Context): String = runCatching {
    context.packageManager.getApplicationInfo(context.packageName, PackageManager.GET_META_DATA)
        .metaData?.getString("com.google.android.geo.API_KEY").orEmpty()
}.getOrDefault("").trim()

private fun metersBetween(a: LatLng, b: LatLng): Float =
    FloatArray(1).also { Location.distanceBetween(a.latitude, a.longitude, b.latitude, b.longitude, it) }[0]

private fun distanceLabel(meters: Float): String =
    if (meters < 1000) "${meters.toInt()} m" else String.format(java.util.Locale.US, "%.1f km", meters / 1000)

/**
 * Hospitals, clinics and pharmacies around the phone's live location, on a map and as a list with
 * distances and directions. Without a Maps key it must not crash: it offers a Google Maps search instead.
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

    var here by remember { mutableStateOf<LatLng?>(null) }
    var hereLabel by remember { mutableStateOf("") }
    var searchedAt by remember { mutableStateOf<LatLng?>(null) }
    var searching by remember { mutableStateOf(false) }
    var searchError by remember { mutableStateOf<String?>(null) }
    var retry by remember { mutableIntStateOf(0) }
    val cameraPositionState = rememberCameraPositionState()

    // Live location: follows the phone for as long as this screen is open.
    DisposableEffect(hasLocationPermission) {
        if (!hasLocationPermission) return@DisposableEffect onDispose { }
        val fused = LocationServices.getFusedLocationProviderClient(context)
        val callback = object : LocationCallback() {
            override fun onLocationResult(result: LocationResult) {
                result.lastLocation?.let { here = LatLng(it.latitude, it.longitude) }
            }
        }
        fused.lastLocation.addOnSuccessListener { last -> if (here == null && last != null) here = LatLng(last.latitude, last.longitude) }
        val request = LocationRequest.Builder(Priority.PRIORITY_HIGH_ACCURACY, 10_000L).setMinUpdateDistanceMeters(20f).build()
        runCatching { fused.requestLocationUpdates(request, callback, Looper.getMainLooper()) }
            .onFailure { Log.w("MedSure", "Location updates unavailable", it) }
        onDispose { fused.removeLocationUpdates(callback) }
    }

    // The first fix centres the map; after that the blue dot moves and the user is free to pan.
    val located = here != null
    LaunchedEffect(located) {
        here?.let { cameraPositionState.position = CameraPosition.fromLatLngZoom(it, 12f) }
    }

    // Search around the live location: on the first fix, after moving a couple of km, and on "Try again".
    val anchor = here?.takeIf { now -> searchedAt?.let { metersBetween(it, now) > RESEARCH_AFTER_M } ?: true } ?: searchedAt
    LaunchedEffect(anchor, retry, placesClient) {
        val center = anchor ?: return@LaunchedEffect
        hereLabel = withContext(Dispatchers.IO) { areaName(context, center) }
        if (placesClient == null) return@LaunchedEffect
        searching = true
        searchError = null
        try {
            val found = findCare(placesClient, center, vm.hospitalName, t["onPapers"])
            searchedAt = center
            vm.rawPlaces.clear()
            vm.rawPlaces.addAll(found)
        } catch (e: Exception) {
            Log.w("MedSure", "Nearby search failed", e)
            searchError = e.message ?: e.javaClass.simpleName
        } finally {
            searching = false
        }
    }

    val filters = listOf("all" to t["fAll"], "hosp" to t["fHosp"], "clinic" to t["fClinic"], "pharm" to t["fPharm"])
    val shown = vm.places
    Column(Modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (!hasLocationPermission) {
            MsCard(bg = Ms.FlagBg, border = Ms.FlagBorder, gap = 6.dp) {
                T(t["locNeeded"], 18, 700, Ms.Brown)
                T(t["locNeededBody"], 15, 400, Ms.Brown, lh = 1.5f)
                MsButton(t["locAllow"], BtnKind.Danger) { permissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION) }
            }
        } else {
            // Where the phone is now: the list and the distances are measured from here.
            MsCard(gap = 4.dp) {
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    Tick(40.dp, Ms.Teal) { Ico(LineIcons.MapPin, androidx.compose.ui.graphics.Color.White, 20.dp) }
                    Column(Modifier.weight(1f)) {
                        T(t["youAreHere"], 13, 700, Ms.Muted)
                        T(if (here == null) t["locFinding"] else hereLabel.ifBlank { t["locLive"] }, 16, 700)
                    }
                }
            }
            if (placesClient != null) {
                Box(Modifier.fillMaxWidth().height(280.dp).clip(RoundedCornerShape(22.dp)).background(Ms.Blister)) {
                    if (here == null) {
                        CircularProgressIndicator(Modifier.align(Alignment.Center))
                    } else {
                        GoogleMap(
                            modifier = Modifier.fillMaxSize(),
                            cameraPositionState = cameraPositionState,
                            properties = MapProperties(isMyLocationEnabled = true), // the blue dot: the phone's live position
                            uiSettings = MapUiSettings(myLocationButtonEnabled = true, zoomControlsEnabled = true),
                        ) {
                            shown.filter { it.lat != 0.0 || it.lng != 0.0 }.forEach { place ->
                                val hue = when (place.type) {
                                    "pharm" -> BitmapDescriptorFactory.HUE_GREEN
                                    "clinic" -> BitmapDescriptorFactory.HUE_ORANGE
                                    else -> BitmapDescriptorFactory.HUE_RED
                                }
                                Marker(
                                    state = MarkerState(position = LatLng(place.lat, place.lng)),
                                    title = place.name, snippet = place.dist,
                                    icon = BitmapDescriptorFactory.defaultMarker(hue),
                                    onClick = { vm.chosen = place.id; false },
                                )
                            }
                        }
                    }
                }
            }
        }

        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            filters.forEach { (id, label) ->
                val count = if (id == "all") vm.rawPlaces.size else vm.rawPlaces.count { it.type == id }
                Chip(if (vm.rawPlaces.isEmpty()) label else "$label · $count", vm.filter == id) { vm.filter = id }
            }
        }
        if (searching) T(t["careFinding"], 14, 400, Ms.Muted)
        searchError?.let { error ->
            MsCard(bg = Ms.FlagBg, border = Ms.FlagBorder, gap = 8.dp) {
                T(t["careError"], 15, 700, Ms.Brown)
                T(error.take(300), 13, 400, Ms.Brown, lh = 1.4f)
                MsButton(t["tryAgain"], BtnKind.Light, height = 44.dp) { retry += 1 }
            }
        }
        if (!searching && searchError == null && shown.isEmpty() && (here != null || placesClient == null)) {
            EmptyNote(when {
                placesClient == null -> t["noPlacesKey"]
                vm.rawPlaces.isEmpty() -> t["noPlaces"]
                else -> t["noPlacesType"]
            })
            MsButton(t["findHosp"], BtnKind.Mari, Modifier.fillMaxWidth(), height = 44.dp) {
                val what = when (vm.filter) { "pharm" -> "pharmacy"; "clinic" -> "clinic"; else -> "hospital" }
                openDirections(context, Place("", "", "$what near me", "", "", "", ""))
            }
        }

        shown.forEach { p ->
            MsCard(border = if (vm.chosen == p.id) Ms.Ink else Ms.Line, gap = 12.dp) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Column(Modifier.weight(1f)) {
                        T(p.name, 17, 700)
                        if (p.meta.isNotEmpty()) T(p.meta, 14, 400, Ms.Muted, lh = 1.35f)
                    }
                    if (p.dist.isNotEmpty()) D(p.dist, 20)
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    val kind = when (p.type) { "pharm" -> t["fPharm"]; "clinic" -> t["fClinic"]; else -> t["fHosp"] }
                    T(kind, 13, 700, Ms.GreenFg, Modifier.clip(RoundedCornerShape(999.dp)).background(Ms.GreenBg).padding(horizontal = 10.dp, vertical = 4.dp))
                    if (p.badge.isNotEmpty()) T(p.badge, 13, 700, Ms.Paper, Modifier.clip(RoundedCornerShape(999.dp)).background(Ms.Ink).padding(horizontal = 10.dp, vertical = 4.dp))
                }
                MsButton(t["directions"], BtnKind.Mari, Modifier.fillMaxWidth(), height = 44.dp) {
                    vm.chosen = p.id
                    openDirections(context, p)
                }
            }
        }
    }
}

/**
 * Opens Google Maps in its own task, with directions starting from the phone's current location.
 * Coming back to MedSure returns to this screen: the app's state is saved when it goes to the
 * background, so it is restored even if Android stopped the app meanwhile.
 */
private fun openDirections(context: Context, p: Place) {
    val uri = if (p.lat != 0.0 || p.lng != 0.0) {
        Uri.parse("https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lng}&travelmode=driving")
    } else {
        Uri.parse("https://www.google.com/maps/search/?api=1&query=" + Uri.encode(p.name))
    }
    val intent = Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    try {
        context.startActivity(Intent(intent).setPackage("com.google.android.apps.maps"))
    } catch (_: ActivityNotFoundException) {
        runCatching { context.startActivity(intent) } // a browser, when Google Maps is not installed
    }
}

/** "Anna Nagar, Chennai": the neighbourhood and city the phone is in. Empty when it cannot be looked up. */
@Suppress("DEPRECATION")
private fun areaName(context: Context, at: LatLng): String = runCatching {
    val address = Geocoder(context, java.util.Locale.getDefault()).getFromLocation(at.latitude, at.longitude, 1)?.firstOrNull()
    listOfNotNull(address?.subLocality, address?.locality ?: address?.subAdminArea).distinct().joinToString(", ")
}.getOrDefault("")

/**
 * Hospitals, pharmacies and clinics within 60 km of [here], nearest first.
 *
 * Each kind is searched on its own, so a city full of pharmacies cannot crowd the hospitals out of
 * the results (one mixed search returns only 20 places in all). For each kind, one search gives the
 * 20 nearest (it can reach 50 km) and a second gives the best-known ones anywhere in the 60 km
 * area, so a big hospital 40 km away is listed even in a city with twenty small ones close by.
 *
 * The hospital named on the discharge papers is looked up too and marked, at its real distance.
 * Throws when every search fails (no network, or the key is not allowed to use Places).
 */
private suspend fun findCare(client: PlacesClient, here: LatLng, dischargeHospital: String, onPapers: String): List<Place> = coroutineScope {
    var failure: Exception? = null

    fun toPlace(g: GmsPlace, type: String, badge: String = ""): Place? {
        val at = g.latLng ?: return null
        val meters = metersBetween(here, at)
        if (meters > RANGE_M) return null
        return Place(
            id = g.id ?: return null, type = type, name = g.name ?: return null, meta = g.address.orEmpty(),
            dist = distanceLabel(meters), open = "", badge = badge, lat = at.latitude, lng = at.longitude, meters = meters,
        )
    }

    suspend fun nearest(category: Category): List<GmsPlace> = try {
        client.searchNearby(
            SearchNearbyRequest.builder(CircularBounds.newInstance(here, NEARBY_MAX_M), PLACE_FIELDS)
                .setIncludedTypes(category.placeTypes)
                .setMaxResultCount(PER_SEARCH)
                .setRankPreference(SearchNearbyRequest.RankPreference.DISTANCE)
                .build()
        ).await().places
    } catch (e: Exception) {
        failure = e
        Log.w("MedSure", "Nearby ${category.type} search failed", e)
        emptyList()
    }

    /** Anything of this kind in the 60 km box around the phone. */
    suspend fun inRange(query: String): List<GmsPlace> = try {
        val dLat = RANGE_M / 111_320.0
        val dLng = RANGE_M / (111_320.0 * kotlin.math.cos(Math.toRadians(here.latitude)).coerceAtLeast(0.01))
        val box = RectangularBounds.newInstance(
            LatLng(here.latitude - dLat, here.longitude - dLng), LatLng(here.latitude + dLat, here.longitude + dLng),
        )
        client.searchByText(
            SearchByTextRequest.builder(query, PLACE_FIELDS).setLocationRestriction(box).setMaxResultCount(PER_SEARCH).build()
        ).await().places
    } catch (e: Exception) {
        failure = e
        Log.w("MedSure", "Text search for '$query' failed", e)
        emptyList()
    }

    val perCategory = CATEGORIES.map { category ->
        async {
            val near = async { nearest(category) }
            val wide = async { inRange(category.query) }
            (near.await() + wide.await()).mapNotNull { toPlace(it, category.type) }
        }
    }
    val papers = async {
        if (dischargeHospital.isBlank()) null
        else inRange(dischargeHospital).firstNotNullOfOrNull { toPlace(it, "hosp", onPapers) }
    }

    val found = perCategory.awaitAll().flatten()
    val own = papers.await()
    if (found.isEmpty() && own == null) failure?.let { throw it }
    // A place can match two kinds (a hospital with a pharmacy): keep it once, under the first kind found.
    (listOfNotNull(own) + found).distinctBy { it.id }.sortedBy { it.meters }
}
