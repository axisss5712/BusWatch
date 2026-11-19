import { CommonModule } from '@angular/common';
import type { OnDestroy, OnInit } from '@angular/core';
import { ChangeDetectorRef, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { IonContent, IonHeader, IonToolbar } from '@ionic/angular';

@Component({
  selector: 'app-home',
  templateUrl: 'home.page.html',
  styleUrls: ['home.page.scss'],
  standalone: true,
  imports: [CommonModule, FormsModule, IonHeader, IonToolbar, IonContent],
})
export class HomePage implements OnInit, OnDestroy {
  private cdr = inject(ChangeDetectorRef);

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
  isBusInactive: boolean = false;

  originStopId: number = 1;
  destStopId: number = 4;
  passengerType: string = 'Regular';
  passengerCount: number = 1;
  ticketSuccessMsg: string = '';
  ticketErrorMsg: string = '';
  autoAlightBanner: string = '';

  dropoffs: any[] = [];
  private previousDropoffMap: { [stopId: number]: { stop_name: string; count: number } } = {};

  remittance: any = {
    total_tickets: 0,
    total_passengers_carried: 0,
    total_fare_collected: 0,
  };

  gpsStatus: string = 'Synced with Route Telemetry';
  private syncTimer?: any;

  showServerConfig: boolean = false;
  originSearchQuery: string = '';
  destSearchQuery: string = '';
  originDropdownOpen: boolean = false;
  destDropdownOpen: boolean = false;

  showLoginPassword: boolean = false;
  showSignupPassword: boolean = false;

  confirmAndSignup(): void {
    if (!this.username.trim() || !this.password.trim()) {
      this.authError = 'Please choose an Employee Username and Password.';
      this.cdr.detectChanges();
      return;
    }
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
    this.ticketSuccessMsg = '';
    this.ticketErrorMsg = '';

    if (this.isBusInactive || !this.activeBus) {
      this.ticketErrorMsg = `Cannot issue ticket: ${this.selectedBusId} is currently marked Inactive by the Dispatcher.`;
      this.cdr.detectChanges();
      return;
    }
    if (Number(this.originStopId) === Number(this.destStopId)) {
      this.ticketErrorMsg = 'Please select a different Origin Stop and Destination Stop.';
      this.cdr.detectChanges();
      return;
    }
    const maxCap = (this.activeBus.max_seated || 30) + (this.activeBus.max_standing || 15);
    const currentPax = this.activeBus.current_passengers || 0;
    if (currentPax + this.passengerCount > maxCap) {
      this.ticketErrorMsg = `Cannot issue ticket: Bus has reached maximum capacity (${currentPax}/${maxCap} passengers).`;
      this.cdr.detectChanges();
      return;
    }
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
    this.cdr.detectChanges();
  }

  toggleDestDropdown(): void {
    this.destDropdownOpen = !this.destDropdownOpen;
    if (this.destDropdownOpen) {
      this.originDropdownOpen = false;
      this.destSearchQuery = '';
    }
    this.cdr.detectChanges();
  }

  selectOriginStop(stopId: number): void {
    this.originStopId = stopId;
    this.originDropdownOpen = false;
    this.originSearchQuery = '';
    this.ticketErrorMsg = '';
    this.cdr.detectChanges();
  }

  selectDestStop(stopId: number): void {
    this.destStopId = stopId;
    this.destDropdownOpen = false;
    this.destSearchQuery = '';
    this.ticketErrorMsg = '';
    this.cdr.detectChanges();
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

  ngOnInit(): void {
    const savedIp = localStorage.getItem('custom_server_url');
    if (savedIp) {
      this.serverUrl = savedIp;
    }
    this.loadFleetList();
  }

  ngOnDestroy(): void {
    if (this.syncTimer) {
      clearInterval(this.syncTimer);
    }
  }

  setAuthMode(mode: 'login' | 'signup'): void {
    this.authMode = mode;
    this.authError = '';
    this.cdr.detectChanges();
  }

  setPassengerType(type: 'Regular' | 'Discounted'): void {
    this.passengerType = type;
    this.cdr.detectChanges();
  }

  adjustPassengerCount(delta: number): void {
    this.passengerCount = Math.max(1, Number(this.passengerCount || 1) + delta);
    this.cdr.detectChanges();
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
    this.cdr.detectChanges();
  }

  async loadFleetList(): Promise<void> {
    try {
      const res = await fetch(`${this.serverUrl}/api/buses`, { cache: 'no-store' });
      if (res.ok) {
        this.availableBuses = await res.json();
        if (
          this.availableBuses.length > 0 &&
          (!this.selectedBusId || !this.availableBuses.some((b) => b.bus_id === this.selectedBusId))
        ) {
          this.selectedBusId = this.availableBuses[0].bus_id;
        }
        this.cdr.detectChanges();
      }
    } catch {
      // Wait until user updates IP and clicks Save & Sync
    }
  }

  formatMoney(val: number | undefined): string {
    return Number(val || 0).toFixed(2);
  }

  private startSyncLoop(): void {
    if (this.syncTimer) {
      clearInterval(this.syncTimer);
    }
    this.syncTimer = setInterval(() => this.refreshAll(), 3000);
  }

  async login(): Promise<void> {
    this.authError = '';
    this.updateServerUrl(this.serverUrl);
    const uname = this.username.trim();
    const pword = this.password.trim();

    if (!uname || !pword) {
      this.authError = 'Please enter both your Employee Username and Password.';
      this.cdr.detectChanges();
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
        this.cdr.detectChanges();
        return;
      }
      this.conductor = data;
      this.selectedBusId = data.assigned_bus_id || this.selectedBusId;
      this.previousDropoffMap = {};
      await this.refreshAll();
      this.startSyncLoop();
      this.cdr.detectChanges();
    } catch {
      this.authError = `Cannot reach ${this.serverUrl}. Please check the Server IP box above.`;
      this.cdr.detectChanges();
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
      this.cdr.detectChanges();
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
        this.cdr.detectChanges();
        return;
      }
      this.conductor = data;
      this.selectedBusId = data.assigned_bus_id || this.selectedBusId;
      this.previousDropoffMap = {};
      await this.refreshAll();
      this.startSyncLoop();
      this.cdr.detectChanges();
    } catch {
      this.authError = `Cannot reach ${this.serverUrl}. Please check the Server IP box above.`;
      this.cdr.detectChanges();
    }
  }

  logout(): void {
    this.conductor = null;
    this.password = '';
    this.authError = '';
    this.activeBus = null;
    this.isBusInactive = false;
    this.ticketSuccessMsg = '';
    this.ticketErrorMsg = '';
    this.autoAlightBanner = '';
    this.dropoffs = [];
    this.previousDropoffMap = {};
    this.remittance = {
      total_tickets: 0,
      total_passengers_carried: 0,
      total_fare_collected: 0,
    };
    if (this.syncTimer) {
      clearInterval(this.syncTimer);
      this.syncTimer = undefined;
    }
    this.loadFleetList();
    this.cdr.detectChanges();
  }

  async refreshAll(): Promise<void> {
    try {
      const resStops = await fetch(`${this.serverUrl}/api/stops`, { cache: 'no-store' });
      if (resStops.ok) {
        this.stops = (await resStops.json()).sort(
          (a: any, b: any) => Number(b.lat) + Number(b.lng) - (Number(a.lat) + Number(a.lng))
        );
        if (this.stops.length > 0) {
          if (!this.stops.some((s) => s.stop_id === Number(this.originStopId))) {
            this.originStopId = this.stops[0].stop_id;
          }
          if (!this.stops.some((s) => s.stop_id === Number(this.destStopId))) {
            this.destStopId = this.stops[this.stops.length - 1].stop_id;
          }
        }
      }

      const resBuses = await fetch(`${this.serverUrl}/api/buses`, { cache: 'no-store' });
      if (resBuses.ok) {
        const buses = await resBuses.json();
        this.availableBuses = buses;
        // Strictly match this conductor's unit — never fall back to another bus if Inactive
        const matchedBus = buses.find((b: any) => b.bus_id === this.selectedBusId) || null;
        this.activeBus = matchedBus;
        this.isBusInactive = !matchedBus;
        this.gpsStatus = matchedBus
          ? `Route Live (${Number(matchedBus.lat).toFixed(4)}, ${Number(matchedBus.lng).toFixed(4)})`
          : 'Unit Inactive';
      }

      const resDrop = await fetch(`${this.serverUrl}/api/tickets/dropoffs/${this.selectedBusId}`, {
        cache: 'no-store',
      });
      if (resDrop.ok) {
        const latestDropoffs: any[] = await resDrop.json();

        // Detect stops that were automatically cleared by geofence telemetry
        const latestIds = new Set(latestDropoffs.map((d) => Number(d.destination_stop_id)));
        Object.keys(this.previousDropoffMap).forEach((stopIdKey) => {
          const sid = Number(stopIdKey);
          if (!latestIds.has(sid) && !this.isBusInactive) {
            const cleared = this.previousDropoffMap[sid];
            this.autoAlightBanner = `Auto-Alighted ${cleared.count} passenger(s) at ${cleared.stop_name}!`;
          }
        });

        const nextMap: { [stopId: number]: { stop_name: string; count: number } } = {};
        latestDropoffs.forEach((d) => {
          nextMap[Number(d.destination_stop_id)] = {
            stop_name: d.stop_name,
            count: Number(d.passengers_dropping_off),
          };
        });
        this.previousDropoffMap = nextMap;
        this.dropoffs = latestDropoffs;
      }

      const resRem = await fetch(`${this.serverUrl}/api/remittance?bus_id=${this.selectedBusId}`, {
        cache: 'no-store',
      });
      if (resRem.ok) {
        const remList = await resRem.json();
        if (remList.length > 0) {
          this.remittance = remList[0];
        }
      }

      this.cdr.detectChanges();
    } catch {
      this.gpsStatus = 'Reconnecting to Server...';
      this.cdr.detectChanges();
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
    this.ticketErrorMsg = '';
    const count = Math.max(1, Number(this.passengerCount || 1));

    try {
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
      const data = await res.json();
      if (res.ok) {
        const savedTotal = this.formatMoney(data.total_fare);
        this.ticketSuccessMsg = `Ticket Issued! +${count} Passenger(s) Boarded (₱${savedTotal})`;
        this.passengerCount = 1;
        await this.refreshAll();
      } else {
        this.ticketErrorMsg = data.detail || 'Could not issue ticket. Please check selected stops and bus status.';
        this.cdr.detectChanges();
      }
    } catch {
      this.ticketErrorMsg = `Cannot reach ${this.serverUrl}. Please check your connection and try again.`;
      this.cdr.detectChanges();
    }
  }
}