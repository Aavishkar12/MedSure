package com.powerbank.medsure.ui.patient

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
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
import com.google.android.libraries.places.api.Places
import com.google.android.libraries.places.api.model.Place as GmsPlace
import com.google.android.libraries.places.api.net.FindCurrentPlaceRequest
import com.google.android.libraries.places.api.net.PlacesClient
import com.google.maps.android.compose.*
import com.powerbank.medsure.state.MedSureViewModel
import com.powerbank.medsure.state.Place
import com.powerbank.medsure.ui.components.*
import com.powerbank.medsure.ui.theme.Ms
import com.powerbank.medsure.i18n.Tx
import kotlinx.coroutines.tasks.await

@SuppressLint("MissingPermission")
@Composable
fun NearbyCareScreen(vm: MedSureViewModel) {
    val context = LocalContext.current
    var hasLocationPermission by remember {
        mutableStateOf(
            ContextCompat.checkSelfPermission(context, Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
        )
    }
    
    val permissionLauncher = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { isGranted ->
        hasLocationPermission = isGranted
    }

    LaunchedEffect(Unit) {
        if (!hasLocationPermission) {
            permissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
        }
    }

    val placesClient = remember {
        if (!Places.isInitialized()) {
            val appInfo = context.packageManager.getApplicationInfo(context.packageName, PackageManager.GET_META_DATA)
            val apiKey = appInfo.metaData.getString("com.google.android.geo.API_KEY") ?: ""
            Places.initialize(context.applicationContext, apiKey)
        }
        Places.createClient(context)
    }

    val fusedLocationClient = remember { LocationServices.getFusedLocationProviderClient(context) }
    var userLocation by remember { mutableStateOf<com.google.android.gms.maps.model.LatLng?>(null) }
    var cameraPositionState = rememberCameraPositionState()

    LaunchedEffect(hasLocationPermission) {
        if (hasLocationPermission) {
            try {
                val location = fusedLocationClient.lastLocation.await()
                if (location != null) {
                    userLocation = com.google.android.gms.maps.model.LatLng(location.latitude, location.longitude)
                    cameraPositionState.position = com.google.android.gms.maps.model.CameraPosition.fromLatLngZoom(userLocation!!, 14f)
                    
                    // Fetch nearby places if not populated
                    if (vm.rawPlaces.isEmpty()) {
                        fetchNearbyPlaces(placesClient, vm)
                    }
                }
            } catch (e: Exception) {
                e.printStackTrace()
                // Fetch nearby places even if location fails, it has a fallback
                if (vm.rawPlaces.isEmpty()) fetchNearbyPlaces(placesClient, vm)
            }
        }
    }

    val t = vm.tx
    val filters = listOf("all" to t["fAll"], "hosp" to t["fHosp"], "clinic" to t["fClinic"], "pharm" to t["fPharm"])

    Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(16.dp)) {
        if (!hasLocationPermission) {
            MsCard(bg = Ms.FlagBg, border = Ms.FlagBorder, gap = 6.dp) {
                T("Location Required", 18, 700, Ms.Brown)
                T("Please grant location permission to find nearby facilities.", 15, 400, Ms.Brown, lh = 1.5f)
                MsButton("Grant Permission", BtnKind.Danger) {
                    permissionLauncher.launch(Manifest.permission.ACCESS_FINE_LOCATION)
                }
            }
        } else {
            // Map
            Box(Modifier.fillMaxWidth().height(250.dp).clip(RoundedCornerShape(22.dp))) {
                if (userLocation == null) {
                    CircularProgressIndicator(Modifier.align(Alignment.Center))
                } else {
                    GoogleMap(
                        modifier = Modifier.fillMaxSize(),
                        cameraPositionState = cameraPositionState,
                        properties = MapProperties(isMyLocationEnabled = true)
                    ) {
                        vm.places.forEach { place ->
                            if (place.lat != 0.0 && place.lng != 0.0) {
                                Marker(
                                    state = MarkerState(position = com.google.android.gms.maps.model.LatLng(place.lat, place.lng)),
                                    title = place.name,
                                    snippet = place.dist
                                )
                            }
                        }
                    }
                }
            }

            // Filters
            Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                filters.forEach { (id, label) -> Chip(label, vm.filter == id) { vm.filter = id } }
            }

            // List
            Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
                vm.places.forEach { p ->
                    val on = vm.chosen == p.id
                    MsCard(border = if (on) Ms.Ink else Ms.Line, gap = 12.dp) {
                        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                            Column(Modifier.weight(1f)) {
                                T(p.name, 17, 700)
                                T(p.meta, 14, 400, Ms.Muted)
                            }
                            D(p.dist, 20)
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            T(p.open, 13, 700, Ms.GreenFg, Modifier.clip(RoundedCornerShape(999.dp)).background(Ms.GreenBg).padding(horizontal = 10.dp, vertical = 4.dp))
                            if (p.badge.isNotEmpty()) T(p.badge, 13, 700, Ms.Paper, Modifier.clip(RoundedCornerShape(999.dp)).background(Ms.Ink).padding(horizontal = 10.dp, vertical = 4.dp))
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            MsButton("Get Directions", BtnKind.Mari, Modifier.weight(1f), height = 44.dp) {
                                val gmmIntentUri = Uri.parse("https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lng}")
                                val mapIntent = Intent(Intent.ACTION_VIEW, gmmIntentUri)
                                mapIntent.setPackage("com.google.android.apps.maps")
                                mapIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                                try {
                                    context.startActivity(mapIntent)
                                } catch (e: Exception) {
                                    // Fallback if Google Maps app is not installed
                                    mapIntent.setPackage(null)
                                    context.startActivity(mapIntent)
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@SuppressLint("MissingPermission")
private suspend fun fetchNearbyPlaces(placesClient: PlacesClient, vm: MedSureViewModel) {
    try {
        val placeFields = listOf(GmsPlace.Field.ID, GmsPlace.Field.NAME, GmsPlace.Field.TYPES, GmsPlace.Field.LAT_LNG, GmsPlace.Field.RATING)
        val request = FindCurrentPlaceRequest.newInstance(placeFields)
        val response = placesClient.findCurrentPlace(request).await()
        
        vm.rawPlaces.clear()
        
        for (placeLikelihood in response.placeLikelihoods) {
            val place = placeLikelihood.place
            val typeNames = place.placeTypes?.map { it.lowercase() } ?: emptyList<String>()
            
            val type = when {
                typeNames.contains("hospital") -> "hosp"
                typeNames.contains("pharmacy") -> "pharm"
                typeNames.contains("clinic") || typeNames.contains("doctor") -> "clinic"
                else -> continue
            }
            
            vm.rawPlaces.add(
                Place(
                    id = place.id ?: "",
                    type = type,
                    name = place.name ?: "Unknown Facility",
                    meta = if (place.rating != null) "Rating: ${place.rating}" else "Healthcare Facility",
                    dist = "Nearby", // In a real app, calculate distance to userLocation
                    open = "Open",
                    badge = if (type == "hosp") "24x7" else "",
                    lat = place.latLng?.latitude ?: 0.0,
                    lng = place.latLng?.longitude ?: 0.0
                )
            )
        }
        
    } catch (e: Exception) {
        e.printStackTrace()
    }
    
    if (vm.rawPlaces.isEmpty()) {
        // Fallback
        val t = vm.tx
        vm.rawPlaces.addAll(listOf(
            Place("h1", "hosp", "[Your discharging hospital]", t["m1"], "4.6 km", t["o24"], t["knows"], 28.6139, 77.2090),
            Place("p1", "pharm", "[Nearest pharmacy]", t["m4"], "0.3 km", t["o10"], "", 28.6140, 77.2100),
        ))
    }
}
