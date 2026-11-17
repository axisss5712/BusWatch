import { CommonModule } from '@angular/common';
import type { OnDestroy, OnInit } from '@angular/core';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Geolocation } from '@capacitor/geolocation';
import { IonContent, IonHeader, IonToolbar } from '@ionic/angular';

@Component({
  selector: 'app-home',
  templateUrl: 'home.page.html',
  styleUrls: ['home.page.scss'],
  standalone: true,
  imports: [IonContent, IonToolbar, IonHeader, IonToolbar, IonHeader, CommonModule, FormsModule, IonContent],
})
export class HomePage implements OnInit, OnDestroy {
  serverUrl: string = 'http://192.168.1.8:8000';
  authMode: 'login' | 'signup' = 'login';

  conductor: any = null;
  username: string = '';
  password: string = '';
  fullName: string = '';
  selectedBusId: string = 'BUS-101';
  authError: string = '';

  stops: any[] = [];
  availableBuses: any[] = [];
  activeBus: any = null;

  originStopId: number = 1;
  destStopId: number = 4;
  passengerType: string = 'Regular';
  passengerCount: number = 1;
  ticketSuccessMsg: string = '';
  autoAlightBanner: string = '';

  dropoffs: any[] = [];
  remittance: any = {
    total_tickets: 0,
    total_passengers_carried: 0,
    total_fare_collected: 0,
  };

  gpsStatus: string = 'GPS Standby';
  private gpsTimer?: any;

  showServerConfig: boolean = false;
  originSearchQuery: string = '';
  destSearchQuery: string = '';
  originDropdownOpen: boolean = false;
  destDropdownOpen: boolean = false;

  showLoginPassword: boolean = false;
  showSignupPassword: boolean = false;

  confirmAndSignup(): void {
    if (confirm('Are you sure you want to create this conductor account?')) {
      this.signup();
    }
  }

  confirmAndLogout(): void {
    if (confirm('Are you sure you want to log out?')) {
      this.logout();
    }
  }

  confirmAndIssueTicket(): void {
    if (confirm(`Are you sure you want to issue this ticket for ${this.passengerCount} passenger(s)?`)) {
      this.issueTicket();
    }
  }
  
  getStopLabel(stopId: number): string {
    const s = this.stops.find((item) => item.stop_id === Number(stopId));
    return s ? `${s.stop_name} (${s.municipality})` : 'Select location';
  }

  toggleOriginDropdown(): void {
    this.originDropdownOpen = !this.originDropdownOpen;
    if (this.originDropdownOpen) {
      this.destDropdownOpen = false;
      this.originSearchQuery = '';
    }
  }

  toggleDestDropdown(): void {
    this.destDropdownOpen = !this.destDropdownOpen;
    if (this.destDropdownOpen) {
      this.originDropdownOpen = false;
      this.destSearchQuery = '';
    }
  }

  selectOriginStop(stopId: number): void {
    this.originStopId = stopId;
    this.originDropdownOpen = false;
    this.originSearchQuery = '';
  }

  selectDestStop(stopId: number): void {
    this.destStopId = stopId;
    this.destDropdownOpen = false;
    this.destSearchQuery = '';
  }

  getFilteredOriginStops(): any[] {
    const q = this.originSearchQuery.trim().toLowerCase();
    if (!q) return this.stops;
    return this.stops.filter(
      (s) =>
        s.stop_name.toLowerCase().includes(q) ||
        s.municipality.toLowerCase().includes(q)
    );
  }

  getFilteredDestStops(): any[] {
    const q = this.destSearchQuery.trim().toLowerCase();
    if (!q) return this.stops;
    return this.stops.filter(
      (s) =>
        s.stop_name.toLowerCase().includes(q) ||
        s.municipality.toLowerCase().includes(q)
    );
  }

  onOriginSearchChange(): void {
    const matches = this.getFilteredOriginStops();
    if (matches.length > 0) {
      this.originStopId = matches[0].stop_id;
    }
  }

  onDestSearchChange(): void {
    const matches = this.getFilteredDestStops();
    if (matches.length > 0) {
      this.destStopId = matches[0].stop_id;
    }
  }

  ngOnInit(): void {
    const savedIp = localStorage.getItem('custom_server_url');
    if (savedIp) {
      this.serverUrl = savedIp;
    }
    this.loadFleetList();
  }

  ngOnDestroy(): void {
    if (this.gpsTimer) {
      clearInterval(this.gpsTimer);
    }
  }

  setAuthMode(mode: 'login' | 'signup'): void {
    this.authMode = mode;
    this.authError = '';
  }

  setPassengerType(type: 'Regular' | 'Discounted'): void {
    this.passengerType = type;
  }

  adjustPassengerCount(delta: number): void {
    this.passengerCount = Math.max(1, Number(this.passengerCount || 1) + delta);
  }

  updateServerUrl(newUrl: string): void {
    let clean = (newUrl || '').trim().replace(/\/+$/, '');
    if (clean && !clean.startsWith('http://') && !clean.startsWith('https://')) {
      clean = 'http://' + clean;
    }
    this.serverUrl = clean;
    localStorage.setItem('custom_server_url', this.serverUrl);
  }

  async saveAndSync(): Promise<void> {
    this.updateServerUrl(this.serverUrl);
    await this.loadFleetList();
    if (this.conductor) {
      await this.refreshAll();
    }
  }

  async loadFleetList(): Promise<void> {
    try {
      const res = await fetch(`${this.serverUrl}/api/buses`);
      if (res.ok) {
        this.availableBuses = await res.json();
        if (this.availableBuses.length > 0 && !this.selectedBusId) {
          this.selectedBusId = this.availableBuses[0].bus_id;
        }
      }
    } catch {
      // Wait until user updates IP and clicks Save & Sync
    }
  }

  formatMoney(val: number | undefined): string {
    return Number(val || 0).toFixed(2);
  }

  async login(): Promise<void> {
    this.authError = '';
    this.updateServerUrl(this.serverUrl);
    const uname = this.username.trim();
    const pword = this.password.trim();

    if (!uname || !pword) {
      this.authError = 'Please enter both your Employee Username and Password.';
      return;
    }
    try {
      const res = await fetch(`${this.serverUrl}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: uname,
          password: pword,
          role: 'Conductor',
          assigned_bus_id: this.selectedBusId,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        this.authError = data.detail || 'Invalid conductor username or password.';
        return;
      }
      this.conductor = data;
      this.selectedBusId = data.assigned_bus_id || this.selectedBusId;
      await this.refreshAll();
      this.gpsTimer = setInterval(() => this.broadcastLiveGps(), 4000);
    } catch {
      this.authError = `Cannot reach ${this.serverUrl}. Please check the Server IP box above.`;
    }
  }

  async signup(): Promise<void> {
    this.authError = '';
    this.updateServerUrl(this.serverUrl);
    const uname = this.username.trim();
    const pword = this.password.trim();
    const fname = this.fullName.trim() || uname;

    if (!uname || !pword) {
      this.authError = 'Please choose an Employee Username and Password.';
      return;
    }
    try {
      const res = await fetch(`${this.serverUrl}/api/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: uname,
          password: pword,
          full_name: fname,
          role: 'Conductor',
          assigned_bus_id: this.selectedBusId,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        this.authError = data.detail || 'Sign-up error. Try another username.';
        return;
      }
      this.conductor = data;
      this.selectedBusId = data.assigned_bus_id || this.selectedBusId;
      await this.refreshAll();
      this.gpsTimer = setInterval(() => this.broadcastLiveGps(), 4000);
    } catch {
      this.authError = `Cannot reach ${this.serverUrl}. Please check the Server IP box above.`;
    }
  }

  logout(): void {
    this.conductor = null;
    if (this.gpsTimer) {
      clearInterval(this.gpsTimer);
    }
  }

  async refreshAll(): Promise<void> {
    try {
      const resStops = await fetch(`${this.serverUrl}/api/stops`);
      this.stops = (await resStops.json()).sort(
        (a: any, b: any) => (Number(b.lat) + Number(b.lng)) - (Number(a.lat) + Number(a.lng))
      );

      const resBuses = await fetch(`${this.serverUrl}/api/buses`);
      const buses = await resBuses.json();
      this.availableBuses = buses;
      this.activeBus = buses.find((b: any) => b.bus_id === this.selectedBusId) || buses[0];

      const resDrop = await fetch(`${this.serverUrl}/api/tickets/dropoffs/${this.selectedBusId}`);
      this.dropoffs = await resDrop.json();

      const resRem = await fetch(`${this.serverUrl}/api/remittance?bus_id=${this.selectedBusId}`);
      const remList = await resRem.json();
      if (remList.length > 0) {
        this.remittance = remList[0];
      }
    } catch {
      // Ignore transient polling errors
    }
  }

  haversineKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const R = 6371;
    const dLat = ((lat2 - lat1) * Math.PI) / 180;
    const dLon = ((lon2 - lon1) * Math.PI) / 180;
    const a =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos((lat1 * Math.PI) / 180) *
        Math.cos((lat2 * Math.PI) / 180) *
        Math.sin(dLon / 2) *
        Math.sin(dLon / 2);
    const straightKm = R * (2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)));
    return straightKm * 1.1625;
  }

  previewDistanceKm(): number {
    const s1 = this.stops.find((s) => s.stop_id === Number(this.originStopId));
    const s2 = this.stops.find((s) => s.stop_id === Number(this.destStopId));
    if (!s1 || !s2 || s1.stop_id === s2.stop_id) return 0;
    return Math.max(0.5, this.haversineKm(Number(s1.lat), Number(s1.lng), Number(s2.lat), Number(s2.lng)));
  }

  previewTotalFare(): number {
    const dist = this.previewDistanceKm();
    if (dist === 0) return 0;
    let unitFare = 15.0 + Math.max(0, dist - 4.0) * 2.5763;
    if (this.passengerType === 'Discounted') {
      unitFare = Math.round(unitFare * 0.8);
    } else {
      unitFare = Math.round(unitFare);
    }
    return unitFare * Math.max(1, Number(this.passengerCount || 1));
  }

  async issueTicket(): Promise<void> {
    this.ticketSuccessMsg = '';
    const count = Math.max(1, Number(this.passengerCount || 1));
    const total = this.formatMoney(this.previewTotalFare());
    const res = await fetch(`${this.serverUrl}/api/tickets/issue`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bus_id: this.selectedBusId,
        issued_by_user_id: this.conductor?.user_id || null,
        origin_stop_id: Number(this.originStopId),
        destination_stop_id: Number(this.destStopId),
        passenger_type: this.passengerType,
        passenger_count: count,
      }),
    });
    if (res.ok) {
      this.ticketSuccessMsg = `Ticket Issued! +${count} Passenger(s) Boarded (₱${total})`;
      this.passengerCount = 1;
      await this.refreshAll();
    }
  }

  async clearDropoff(destinationStopId: number): Promise<void> {
    await fetch(`${this.serverUrl}/api/tickets/dropoff`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        bus_id: this.selectedBusId,
        destination_stop_id: destinationStopId,
      }),
    });
    await this.refreshAll();
  }

  async broadcastLiveGps(): Promise<void> {
    if (!this.activeBus) return;
    try {
      const pos = await Geolocation.getCurrentPosition({
        enableHighAccuracy: true,
        timeout: 3000,
      });
      const lat = pos.coords.latitude;
      const lng = pos.coords.longitude;
      this.gpsStatus = `GPS Live (${lat.toFixed(4)}, ${lng.toFixed(4)})`;

      await fetch(`${this.serverUrl}/api/buses/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bus_id: this.selectedBusId,
          lat,
          lng,
          current_passengers: this.activeBus.current_passengers,
          max_seated: this.activeBus.max_seated,
          max_standing: this.activeBus.max_standing,
          event_source: 'Conductor GPS',
        }),
      });

      for (const d of this.dropoffs) {
        if (this.haversineKm(lat, lng, Number(d.lat), Number(d.lng)) <= 0.18) {
          await this.clearDropoff(d.destination_stop_id);
          this.autoAlightBanner = `Auto-Alighted ${d.passengers_dropping_off} passenger(s) at ${d.stop_name}!`;
        }
      }
      await this.refreshAll();
    } catch {
      this.gpsStatus = 'Synced with Route Telemetry';
      await this.refreshAll();
    }
  }
}