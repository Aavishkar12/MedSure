package com.powerbank.medsure.state

import android.app.Application
import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

/**
 * Closing the app and opening it again must land on the same screen with the same data.
 * Each test puts one ViewModel in a state, saves it, and builds a second one the way Android does
 * after the app was closed or stopped in the background.
 */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], application = Application::class)
class PersistenceTest {
    private val app: Application get() = ApplicationProvider.getApplicationContext()
    private val prefs get() = app.getSharedPreferences("medsure_state", Context.MODE_PRIVATE)

    @Before
    fun clean() {
        prefs.edit().clear().commit()
    }

    /** What the app does when it goes to the background, then a fresh start. */
    private fun MedSureViewModel.reopen(): MedSureViewModel {
        save()
        return MedSureViewModel(app)
    }

    @Test
    fun firstLaunchStartsAtLanguage() {
        val vm = MedSureViewModel(app)
        assertEquals(Stage.Lang, vm.stage)
        assertTrue(vm.doses.isEmpty()) // no sample medicines before any paper is read
        assertTrue(vm.billRows.isEmpty())
        assertTrue(vm.flags.isEmpty())
    }

    @Test
    fun signUpScreensComeBack() {
        val vm = MedSureViewModel(app)
        vm.lang = "en"; vm.loginRole = Role.Family; vm.stage = Stage.Details
        vm.onPhone("9876512345"); vm.onEmail("a@b.in")
        var again = vm.reopen()
        assertEquals(Stage.Details, again.stage)
        assertEquals(Role.Family, again.loginRole)
        assertEquals("9876512345", again.phone)

        again.stage = Stage.Otp; again.onOtpP("123456")
        again = again.reopen()
        assertEquals(Stage.Otp, again.stage)
        assertEquals("", again.otpP) // one-time codes are never written to the phone
    }

    @Test
    fun onboardingStepAndAnswersComeBack() {
        val vm = MedSureViewModel(app)
        vm.lang = "en"; vm.stage = Stage.Onboarding
        vm.onbFullName = "Ramesh Iyer"; vm.onbAge = "57"; vm.onbGender = "Male"; vm.onbBloodGroup = "B+"
        vm.onboardingStep = 3; vm.onbInsCompany = "Suraksha"
        vm.onbFamilyMembers.add(OnboardingFamilyMember("Lakshmi", "9876500001", true))
        val again = vm.reopen()
        assertEquals(Stage.Onboarding, again.stage)
        assertEquals(3, again.onboardingStep)
        assertEquals("Ramesh Iyer", again.onbFullName)
        assertEquals("Suraksha", again.onbInsCompany)
        assertEquals("Lakshmi", again.onbFamilyMembers.single().name)
    }

    @Test
    fun readingPapersResumesInsteadOfStartingOver() {
        val vm = MedSureViewModel(app)
        vm.lang = "en"; vm.stage = Stage.Processing
        assertEquals(Stage.Processing, vm.reopen().stage)
    }

    @Test
    fun patientComesBackOnTheSameTabMidCheckIn() {
        val vm = MedSureViewModel(app)
        vm.lang = "en"; vm.role = Role.Patient; vm.stage = Stage.App
        vm.onbFullName = "Ramesh Iyer"
        vm.ptab = PTab.Checkin
        vm.ans.add(0); vm.step = 1 // answered the first question
        vm.note = "feet feel tight"
        val again = vm.reopen()
        assertEquals(Stage.App, again.stage)
        assertEquals(PTab.Checkin, again.ptab)
        assertEquals(1, again.step)
        assertEquals(listOf(0), again.ans.toList())
        assertEquals("feet feel tight", again.note)
        assertEquals("Ramesh", again.me)
    }

    @Test
    fun helpTabAndCareTabComeBack() {
        val vm = MedSureViewModel(app)
        vm.lang = "en"; vm.stage = Stage.App; vm.ptab = PTab.Help; vm.filter = "pharm"
        var again = vm.reopen()
        assertEquals(PTab.Help, again.ptab) // returning from Google Maps lands back on Help
        assertEquals("pharm", again.filter)

        again.ptab = PTab.Care; again.care = "visit"
        again = again.reopen()
        assertEquals(PTab.Care, again.ptab)
        assertEquals("visit", again.care)
    }

    @Test
    fun familyComesBackWithOpenSheetAndSettings() {
        val vm = MedSureViewModel(app)
        vm.lang = "en"; vm.role = Role.Family; vm.loginRole = Role.Family; vm.stage = Stage.App
        vm.ftab = FTab.Claim; vm.sheet = Sheet.Approve
        var again = vm.reopen()
        assertEquals(Role.Family, again.role)
        assertEquals(FTab.Claim, again.ftab)
        assertEquals(Sheet.Approve, again.sheet)

        again.sheet = null; again.overlay = Overlay.Settings
        again.openAdd(); again.fName = "Meena"; again.onFPhone("9876500002")
        again = again.reopen()
        assertEquals(Overlay.Add, again.overlay)
        assertEquals("Meena", again.fName)
        assertEquals("9876500002", again.fPhone)
        again.closeOverlay() // Back from "Add" still returns to Settings, as before the restart
        assertEquals(Overlay.Settings, again.overlay)
    }

    @Test
    fun dataReadFromPapersIsShownStraightAfterRestart() {
        val vm = MedSureViewModel(app)
        vm.lang = "en"; vm.stage = Stage.App
        vm.save()
        // What the backend sent for this case, as the app stores it.
        val card = """{"document_id":1,"data":{"hospital":"Greenfield Hospital","discharge_date":"06-10-2026",
            "diagnosis":{"name":"Acute calculous cholecystitis","plain":"Inflamed gallbladder."},
            "medicines":[{"name":"Tab Cefuroxime","dose":"500 mg","schedule":"twice a day","days":5}],
            "warning_signs":[{"text":"Fever above 101 F"},{"text":"Yellowing of eyes"}],
            "follow_ups":[{"what":"Suture removal","when":"13-10-2026"}]}}"""
        val bill = """{"total":2450,"items":[{"id":7,"description":"ECG","amount":450,"worth_asking":true,"ask_reason":"Listed twice?"},
            {"id":8,"description":"Ultrasound","amount":2000}]}"""
        val coverage = """{"data":{"headline":"About Rs 1,800 looks claimable.","method":"ai",
            "totals":{"billed":2450,"estimated_claimable":1800,"estimated_out_of_pocket":650},"items":[]}}"""
        val policy = """{"data":{"insurer":"Suraksha General","policy_number":"SGI/1","sum_insured":300000,"claim_submission_deadline":"Within 15 days of discharge"}}"""
        val draft = """{"id":3,"body":"To the Claims Manager...","status":"draft"}"""
        val state = JSONObject(prefs.getString("state", null)!!)
            .put("cardJson", card).put("billJson", bill).put("coverageJson", coverage)
            .put("policyJson", policy).put("claimDraftJson", draft)
        prefs.edit().putString("state", state.toString()).commit()

        val again = MedSureViewModel(app)
        assertEquals("Tab Cefuroxime", again.doses.single().name)
        assertEquals("Greenfield Hospital", again.hospitalName)
        assertEquals(listOf("ECG" to "₹450", "Ultrasound" to "₹2,000"), again.billRows)
        assertEquals("b7", again.flags.single().id)
        assertEquals(1800.0, again.coverage!!.estimatedClaimable, 0.0)
        assertEquals("Suraksha General", again.policy!!.insurer)
        assertEquals("draft", again.claimDraft!!.status)
        assertNotNull(again.claimDeadline)
        // Check-in questions come from this patient's own warning signs.
        assertTrue(again.questions[0].first.contains("Fever above 101 F"))
        assertTrue(again.questions[1].first.contains("Yellowing of eyes"))
        assertEquals(3, again.questions.size)
        // Places on the Help tab come only from the live search around the phone.
        assertTrue(again.places.isEmpty())
    }

    @Test
    fun filterChipsShowOnlyTheirOwnKindNearestFirst() {
        val vm = MedSureViewModel(app)
        vm.rawPlaces.addAll(listOf(
            Place("h1", "hosp", "City Hospital", "", "1.2 km", "", "", 13.0, 80.0, 1200f),
            Place("p1", "pharm", "Apollo Pharmacy", "", "300 m", "", "", 13.0, 80.0, 300f),
            Place("c1", "clinic", "Family Clinic", "", "2.0 km", "", "", 13.0, 80.0, 2000f),
            Place("h2", "hosp", "District Hospital", "", "41.0 km", "", "", 13.3, 80.2, 41000f),
        ))
        vm.filter = "all"; assertEquals(4, vm.places.size)
        vm.filter = "hosp"; assertEquals(listOf("h1", "h2"), vm.places.map { it.id })
        vm.filter = "pharm"; assertEquals(listOf("p1"), vm.places.map { it.id })
        vm.filter = "clinic"; assertEquals(listOf("c1"), vm.places.map { it.id })
    }

    @Test
    fun logoutLeavesNothingBehind() {
        val vm = MedSureViewModel(app)
        vm.lang = "en"; vm.stage = Stage.App; vm.ptab = PTab.Help; vm.onbFullName = "Ramesh"
        vm.logout()
        val again = vm.reopen()
        assertEquals(Stage.Welcome, again.stage)
        assertEquals("", again.onbFullName)
        assertNull(again.dischargeCardData)
        assertEquals(PTab.Today, again.ptab)
    }
}
