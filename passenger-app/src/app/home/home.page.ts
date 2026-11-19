import { CommonModule } from '@angular/common';
import type { OnDestroy, OnInit } from '@angular/core';
import { ChangeDetectorRef, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { IonContent, IonHeader, IonToolbar } from '@ionic/angular';
import * as L from 'leaflet';

@Component({
  selector: 'app-home',
  templateUrl: 'home.page.html',
  styleUrls: ['home.page.scss'],
  standalone: true,
  imports: [IonToolbar, IonHeader, CommonModule, FormsModule, IonContent],
})
export class HomePage implements OnInit, OnDestroy {
  protected readonly Math = Math;
  private cdr = inject(ChangeDetectorRef);

  serverUrl: string = 'http://192.168.1.8:8000';
  authMode: 'login' | 'signup' = 'login';

  loggedInUser: any = null;
  authUsername: string = '';
  authPassword: string = '';
  authFullName: string = '';
  authMessage: string = '';

  stops: any[] = [];
  buses: any[] = [];

  selectedStopId: number = 1;
  destinationStopId: number = 6;

  customLat: number = 15.5565427;
  customLng: number = 121.0925970;
  exactLocationStatus: string = 'Tap anywhere on the map below to move your pin.';

  fbBusId: string = 'BUS-101';
  fbCategory: string = 'Left Item / Lost & Found';
  fbMessage: string = '';
  fbStatus: string = '';
  fbError: string = '';

  private map?: L.Map;
  private busMarkers: { [key: string]: L.Marker } = {};
  private stopMarkers: L.Layer[] = [];
  private exactLocationMarker?: L.Marker;
  private busVectors: {
    [key: string]: {
      lat: number;
      lng: number;
      dLat: number;
      dLng: number;
      timestamp: number;
      speedKmh: number;
    };
  } = {};
  private routePolyline?: L.Polyline;
  private pollTimer?: any;
  private stopPollCounter: number = 0;

  showServerConfig: boolean = false;
  mapSearchQuery: string = '';
  showBusList: boolean = true;
  expandedBusIds: { [key: string]: boolean } = {};

  showLoginPassword: boolean = false;
  showSignupPassword: boolean = false;

  toggleBusList(): void {
    this.showBusList = !this.showBusList;
    this.cdr.detectChanges();
  }

  toggleBusCard(busId: string, idx: number): void {
    const currentlyExpanded = this.isBusExpanded(busId, idx);
    this.expandedBusIds[busId] = !currentlyExpanded;
    this.cdr.detectChanges();
  }

  isBusExpanded(busId: string, idx: number): boolean {
    if (busId in this.expandedBusIds) {
      return this.expandedBusIds[busId];
    }
    return idx === 0;
  }

  async searchLocationOnMap(): Promise<void> {
    const q = this.mapSearchQuery.trim();
    if (!q || !this.map) return;

    const qLower = q.toLowerCase();
    const matchedStop = this.stops.find(
      (s) =>
        s.stop_name.toLowerCase().includes(qLower) ||
        s.municipality.toLowerCase().includes(qLower)
    );
    if (matchedStop) {
      this.focusStop(matchedStop);
      return;
    }

    try {
      const url = `https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(
        q + ', Nueva Ecija, Philippines'
      )}&limit=1`;
      const res = await fetch(url);
      const data = await res.json();
      if (data && data.length > 0) {
        this.customLat = parseFloat(data[0].lat);
        this.customLng = parseFloat(data[0].lon);
        this.selectedStopId = 0;
        const shortLabel = data[0].display_name.split(',')[0];
        this.exactLocationStatus = `Pinned location: ${shortLabel} (Tap map to adjust)`;
        this.updateExactLocationMarker(true);
      } else {
        this.exactLocationStatus = `Could not find "${q}". Tap anywhere on the map to pin your spot.`;
      }
      this.cdr.detectChanges();
    } catch {
      this.exactLocationStatus = 'Map search unavailable offline. Tap directly on the map to pin your spot.';
      this.cdr.detectChanges();
    }
  }

  ngOnInit(): void {
    const savedIp = localStorage.getItem('custom_server_url');
    if (savedIp) {
      this.serverUrl = savedIp;
    } else if (
      window.location.hostname &&
      window.location.hostname !== 'localhost' &&
      window.location.hostname !== '127.0.0.1'
    ) {
      this.serverUrl = `http://${window.location.hostname}:8000`;
    }
  }

  ngOnDestroy(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
    }
    if (this.map) {
      this.map.remove();
      this.map = undefined;
    }
  }

  confirmAndSignup(): void {
    if (!this.authUsername.trim() || !this.authPassword.trim()) {
      this.authMessage = 'Please choose a Username and Password to create your account.';
      this.cdr.detectChanges();
      return;
    }
    if (confirm('Are you sure you want to create this account?')) {
      this.signup();
    }
  }

  confirmAndLogout(): void {
    if (confirm('Are you sure you want to log out?')) {
      this.logout();
    }
  }

  confirmAndSubmitFeedback(): void {
    this.fbStatus = '';
    this.fbError = '';
    if (!this.fbBusId) {
      this.fbError = 'No active mini-bus selected to report.';
      this.cdr.detectChanges();
      return;
    }
    if (!this.fbMessage.trim()) {
      this.fbError = 'Please type the details of your report before sending.';
      this.cdr.detectChanges();
      return;
    }
    if (confirm('Are you sure you want to send this report to the dispatcher?')) {
      this.submitFeedback();
    }
  }

  setAuthMode(mode: 'login' | 'signup'): void {
    this.authMode = mode;
    this.authMessage = '';
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

  async saveAndConnect(): Promise<void> {
    this.updateServerUrl(this.serverUrl);
    await this.syncAll();
    this.cdr.detectChanges();
  }

  private startPolling(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
    }
    this.pollTimer = setInterval(() => {
      this.syncBuses();
      this.stopPollCounter++;
      if (this.stopPollCounter % 5 === 0) {
        this.checkIfStopsUpdated();
      }
    }, 2000);
  }

  async login(): Promise<void> {
    this.authMessage = '';
    this.updateServerUrl(this.serverUrl);
    const uname = this.authUsername.trim();
    const pword = this.authPassword.trim();

    if (!uname || !pword) {
      this.authMessage = 'Please enter both your Username and Password.';
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
          role: 'Passenger',
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        this.authMessage = data.detail || 'Invalid username or password.';
        this.cdr.detectChanges();
        return;
      }
      this.loggedInUser = data;
      this.cdr.detectChanges();
      setTimeout(() => {
        this.initMap();
        this.syncAll();
        this.startPolling();
      }, 200);
    } catch {
      this.authMessage = `Cannot connect to ${this.serverUrl}. Please check the Server IP box above.`;
      this.cdr.detectChanges();
    }
  }

  async signup(): Promise<void> {
    this.authMessage = '';
    this.updateServerUrl(this.serverUrl);
    const uname = this.authUsername.trim();
    const pword = this.authPassword.trim();
    const fname = this.authFullName.trim() || uname;

    if (!uname || !pword) {
      this.authMessage = 'Please choose a Username and Password to create your account.';
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
          role: 'Passenger',
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        this.authMessage = data.detail || 'Sign-up failed. Try another username.';
        this.cdr.detectChanges();
        return;
      }
      this.loggedInUser = data;
      this.cdr.detectChanges();
      setTimeout(() => {
        this.initMap();
        this.syncAll();
        this.startPolling();
      }, 200);
    } catch {
      this.authMessage = `Cannot connect to ${this.serverUrl}. Please check the Server IP box above.`;
      this.cdr.detectChanges();
    }
  }

  logout(): void {
    this.loggedInUser = null;
    this.authPassword = '';
    this.authMessage = '';
    this.fbMessage = '';
    this.fbStatus = '';
    this.fbError = '';
    this.mapSearchQuery = '';
    this.busVectors = {};
    this.expandedBusIds = {};
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = undefined;
    }
    if (this.map) {
      this.map.remove();
      this.map = undefined;
      this.busMarkers = {};
      this.stopMarkers = [];
      this.exactLocationMarker = undefined;
    }
    this.cdr.detectChanges();
  }

  initMap(): void {
    if (this.map) return;

    this.map = L.map('passengerMap', {
      minZoom: 10,
      maxZoom: 18,
    }).setView([15.5565427, 121.0925970], 11);

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap contributors',
      noWrap: true,
    }).addTo(this.map);

    this.map.on('click', (e: L.LeafletMouseEvent) => {
      const clickedLat = e.latlng.lat;
      const clickedLng = e.latlng.lng;

      const nearbyOfficialStop = this.stops.find(
        (s) => this.haversineKm(clickedLat, clickedLng, Number(s.lat), Number(s.lng)) <= 0.15
      );

      if (nearbyOfficialStop) {
        this.focusStop(nearbyOfficialStop);
        return;
      }

      this.customLat = clickedLat;
      this.customLng = clickedLng;
      this.selectedStopId = 0;
      this.exactLocationStatus = `Custom pin placed (${clickedLat.toFixed(4)}, ${clickedLng.toFixed(4)}). Tap map to move.`;
      this.updateExactLocationMarker(false);
      this.cdr.detectChanges();
    });

    setTimeout(() => this.map?.invalidateSize(), 250);
  }

  async syncAll(): Promise<void> {
    await this.loadStops();
    await this.syncBuses();
  }

  async checkIfStopsUpdated(): Promise<void> {
    try {
      const res = await fetch(`${this.serverUrl}/api/stops`, { cache: 'no-store' });
      if (res.ok) {
        const latestStops: any[] = await res.json();
        const oldSig = this.stops.map((s) => `${s.stop_id}:${s.stop_name}`).join('|');
        const newSig = latestStops
          .sort((a, b) => Number(b.lat) + Number(b.lng) - (Number(a.lat) + Number(a.lng)))
          .map((s) => `${s.stop_id}:${s.stop_name}`)
          .join('|');
        if (oldSig !== newSig) {
          await this.loadStops();
        }
      }
    } catch {
      // Ignore transient network errors
    }
  }

  onStopChange(): void {
    if (Number(this.selectedStopId) === 0) {
      this.detectPassengerGps();
      return;
    }
    if (this.exactLocationMarker && this.map) {
      this.map.removeLayer(this.exactLocationMarker);
      this.exactLocationMarker = undefined;
    }
    const chosen = this.stops.find((s) => s.stop_id === Number(this.selectedStopId));
    if (chosen) {
      this.focusStop(chosen);
    }
    this.cdr.detectChanges();
  }

  selectExactLocationOption(): void {
    this.selectedStopId = 0;
    this.detectPassengerGps();
  }

  detectPassengerGps(): void {
    this.exactLocationStatus = 'Detecting your GPS location... (or tap anywhere on the map below)';
    this.updateExactLocationMarker(true);
    this.cdr.detectChanges();

    if (navigator.geolocation) {
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          this.customLat = pos.coords.latitude;
          this.customLng = pos.coords.longitude;
          this.selectedStopId = 0;
          this.exactLocationStatus = `Using your live GPS location (${this.customLat.toFixed(4)}, ${this.customLng.toFixed(4)}). Tap map to adjust.`;
          this.updateExactLocationMarker(true);
          this.cdr.detectChanges();
        },
        () => {
          this.exactLocationStatus = 'GPS unavailable — tap anywhere on the map below to pin your exact waiting spot.';
          this.updateExactLocationMarker(true);
          this.cdr.detectChanges();
        },
        { enableHighAccuracy: true, timeout: 4000, maximumAge: 10000 }
      );
    } else {
      this.exactLocationStatus = 'Tap anywhere on the map below to pin your exact waiting spot.';
      this.cdr.detectChanges();
    }
  }

  updateExactLocationMarker(panMap: boolean = false): void {
    if (!this.map) return;

    const html = `
      <svg xmlns="http://www.w3.org/2000/svg" width="28" height="28" viewBox="0 0 24 24" fill="#1b5e20" stroke="#ffffff" stroke-width="2">
        <path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"/>
        <circle cx="12" cy="9" r="2.5" fill="#ffffff"/>
      </svg>
    `;

    const icon = L.divIcon({
      html,
      className: '',
      iconSize: [28, 28],
      iconAnchor: [14, 28],
      popupAnchor: [0, -28],
    });

    if (this.exactLocationMarker) {
      this.exactLocationMarker.setLatLng([this.customLat, this.customLng]).setIcon(icon);
    } else {
      this.exactLocationMarker = L.marker([this.customLat, this.customLng], { icon })
        .addTo(this.map)
        .bindPopup('<b>Your Exact Waiting Location</b><br>Tap anywhere on the map to move this pin.');
    }

    if (panMap) {
      this.map.setView([this.customLat, this.customLng], 14);
    }
  }

  getActiveOrigin(): { stop_id: number; stop_name: string; lat: number; lng: number; stop_order?: number } | null {
    if (Number(this.selectedStopId) === 0) {
      return {
        stop_id: 0,
        stop_name: 'Your Exact Location',
        lat: Number(this.customLat),
        lng: Number(this.customLng),
      };
    }
    return this.stops.find((s) => s.stop_id === Number(this.selectedStopId)) || this.stops[0] || null;
  }

  async loadStops(): Promise<void> {
    try {
      const res = await fetch(`${this.serverUrl}/api/stops`, { cache: 'no-store' });
      const rawStops: any[] = await res.json();

      this.stops = rawStops.sort(
        (a, b) => Number(b.lat) + Number(b.lng) - (Number(a.lat) + Number(a.lng))
      );

      // Keep selected stops valid if Dispatcher deleted a stop
      if (this.stops.length > 0) {
        if (this.selectedStopId !== 0 && !this.stops.some((s) => s.stop_id === Number(this.selectedStopId))) {
          this.selectedStopId = this.stops[0].stop_id;
        }
        if (!this.stops.some((s) => s.stop_id === Number(this.destinationStopId))) {
          this.destinationStopId = this.stops[this.stops.length - 1].stop_id;
        }
      }

      this.cdr.detectChanges();
      if (!this.map || this.stops.length === 0) return;

      this.stopMarkers.forEach((m) => this.map?.removeLayer(m));
      this.stopMarkers = [];

      const straightFallbackCoords: L.LatLngExpression[] = [];
      this.stops.forEach((s) => {
        const lat = Number(s.lat);
        const lng = Number(s.lng);
        straightFallbackCoords.push([lat, lng]);

        const marker = L.circleMarker([lat, lng], {
          radius: 8,
          fillColor: '#B47792',
          color: '#2D262B',
          weight: 2,
          fillOpacity: 0.95,
        })
          .addTo(this.map!)
          .bindPopup(`<b>${s.stop_name}</b><br>${s.municipality}`);

        marker.on('click', (ev: L.LeafletMouseEvent) => {
          L.DomEvent.stopPropagation(ev);
          this.focusStop(s);
          marker.openPopup();
        });

        this.stopMarkers.push(marker);
      });

      let routeCoords: L.LatLngExpression[] = straightFallbackCoords;
      try {
        const coordString = this.stops
          .map((s) => `${Number(s.lng)},${Number(s.lat)}`)
          .join(';');
        const osrmRes = await fetch(
          `https://router.project-osrm.org/route/v1/driving/${coordString}?overview=full&geometries=geojson`
        );
        if (osrmRes.ok) {
          const osrmData = await osrmRes.json();
          if (osrmData.routes?.length > 0) {
            routeCoords = osrmData.routes[0].geometry.coordinates.map(
              (c: [number, number]) => [c[1], c[0]] as L.LatLngExpression
            );
          }
        }
      } catch {
        // Fallback if offline
      }

      if (this.routePolyline) {
        this.map.removeLayer(this.routePolyline);
      }
      this.routePolyline = L.polyline(routeCoords, {
        color: '#B47792',
        weight: 5,
        opacity: 0.9,
      }).addTo(this.map);

      this.cdr.detectChanges();
    } catch {
      // Ignore transient network errors during polling
    }
  }

  async syncBuses(): Promise<void> {
    try {
      const res = await fetch(`${this.serverUrl}/api/buses`, { cache: 'no-store' });
      const incomingBuses: any[] = await res.json();
      const now = Date.now();

      incomingBuses.forEach((b) => {
        const curLat = Number(b.lat);
        const curLng = Number(b.lng);
        const prev = this.busVectors[b.bus_id];

        if (!prev) {
          this.busVectors[b.bus_id] = {
            lat: curLat,
            lng: curLng,
            dLat: 0,
            dLng: 0,
            timestamp: now,
            speedKmh: 28.0,
          };
        } else {
          const distStepKm = this.haversineKm(prev.lat, prev.lng, curLat, curLng);
          const elapsedHours = (now - prev.timestamp) / 3600000;

          if (distStepKm > 0.002 && elapsedHours > 0) {
            const rawSpeed = distStepKm / elapsedHours;
            const clampedSpeed = Math.min(75.0, Math.max(8.0, rawSpeed));
            const smoothedSpeed = prev.speedKmh * 0.6 + clampedSpeed * 0.4;

            this.busVectors[b.bus_id] = {
              lat: curLat,
              lng: curLng,
              dLat: curLat - prev.lat,
              dLng: curLng - prev.lng,
              timestamp: now,
              speedKmh: smoothedSpeed,
            };
          }
        }
      });

      this.buses = [...incomingBuses];

      // Keep Feedback dropdown pointing to a valid active bus
      if (this.buses.length > 0 && !this.buses.some((b) => b.bus_id === this.fbBusId)) {
        this.fbBusId = this.buses[0].bus_id;
      } else if (this.buses.length === 0) {
        this.fbBusId = '';
      }

      this.cdr.detectChanges();

      if (!this.map) return;

      const activeIds = new Set(this.buses.map((b) => b.bus_id));
      Object.keys(this.busMarkers).forEach((id) => {
        if (!activeIds.has(id)) {
          this.map?.removeLayer(this.busMarkers[id]);
          delete this.busMarkers[id];
        }
      });

      this.buses.forEach((b) => {
        const html = `<div style="position:absolute;left:0;top:0;transform:translate(-50%,-50%);display:inline-flex;align-items:center;justify-content:center;width:max-content;box-sizing:border-box;background:#B47792;color:#fff;padding:3px 8px;border-radius:999px;font-weight:700;font-size:11px;line-height:1.2;border:2px solid #FA9EBC;white-space:nowrap;box-shadow:0 2px 5px rgba(0,0,0,0.25);">${b.bus_id}</div>`;
        const icon = L.divIcon({
          html,
          className: '',
          iconSize: [0, 0],
          iconAnchor: [0, 0],
          popupAnchor: [0, -14],
        });

        const popupHtml = `<b>${b.bus_id} (${b.plate_number})</b><br>Driver: ${b.driver_name}<br>Conductor: ${b.conductor_name}<br>Status: ${b.status}`;

        if (this.busMarkers[b.bus_id]) {
          this.busMarkers[b.bus_id].setLatLng([b.lat, b.lng]).setIcon(icon).setPopupContent(popupHtml);
        } else {
          this.busMarkers[b.bus_id] = L.marker([b.lat, b.lng], { icon })
            .addTo(this.map!)
            .bindPopup(popupHtml);
        }
      });
    } catch {
      // Ignore transient polling errors
    }
  }

  focusStop(s: any): void {
    this.selectedStopId = s.stop_id;
    if (this.exactLocationMarker && this.map) {
      this.map.removeLayer(this.exactLocationMarker);
      this.exactLocationMarker = undefined;
    }
    if (this.map) {
      this.map.setView([Number(s.lat), Number(s.lng)], 14);
    }
    this.cdr.detectChanges();
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

  isPassengerGoingSouth(origin: any, dest: any): boolean {
    if (!origin || !dest) return true;
    if (origin.stop_order !== undefined && dest.stop_order !== undefined && origin.stop_id !== 0) {
      return dest.stop_order >= origin.stop_order;
    }
    return Number(dest.lat) + Number(dest.lng) <= Number(origin.lat) + Number(origin.lng);
  }

  getPassengerDirectionLabel(): string {
    const origin = this.getActiveOrigin();
    const dest = this.stops.find((s) => s.stop_id === Number(this.destinationStopId));
    if (!origin || !dest || (origin.stop_id !== 0 && origin.stop_id === dest.stop_id)) {
      return 'Select different Origin & Destination';
    }
    return this.isPassengerGoingSouth(origin, dest)
      ? 'Towards Cabanatuan City'
      : 'Towards Bongabon Terminal';
  }

  getPassengerTripDistance(): number {
    const origin = this.getActiveOrigin();
    const dest = this.stops.find((s) => s.stop_id === Number(this.destinationStopId));
    if (!origin || !dest || (origin.stop_id !== 0 && origin.stop_id === dest.stop_id)) return 0;
    return Math.max(0.5, this.haversineKm(Number(origin.lat), Number(origin.lng), Number(dest.lat), Number(dest.lng)));
  }

  getPassengerRegularFare(): number {
    const dist = this.getPassengerTripDistance();
    if (dist === 0) return 0;
    return 15.0 + Math.max(0, dist - 4.0) * 2.5763;
  }

  getBusStatusInfo(b: any): { priority: number; badge: string } {
    const origin = this.getActiveOrigin();
    const dest = this.stops.find((s) => s.stop_id === Number(this.destinationStopId));
    if (!origin) {
      return { priority: 1, badge: 'Calculating arrival...' };
    }

    const curLat = Number(b.lat);
    const curLng = Number(b.lng);
    const stopLat = Number(origin.lat);
    const stopLng = Number(origin.lng);
    const dist = this.haversineKm(curLat, curLng, stopLat, stopLng);

    const hasValidTrip = !!(dest && (origin.stop_id === 0 || origin.stop_id !== dest.stop_id));
    const passengerGoingSouth = this.isPassengerGoingSouth(origin, dest);

    const firstStop = this.stops[0];
    const lastStop = this.stops[this.stops.length - 1];
    const atNorthTerminal =
      !!firstStop && this.haversineKm(curLat, curLng, Number(firstStop.lat), Number(firstStop.lng)) <= 0.2;
    const atSouthTerminal =
      !!lastStop && this.haversineKm(curLat, curLng, Number(lastStop.lat), Number(lastStop.lng)) <= 0.2;

    const vec = this.busVectors[b.bus_id];
    const hasMoved = !!vec && (Math.abs(vec.dLat) > 0.00001 || Math.abs(vec.dLng) > 0.00001);

    let busGoingSouth: boolean | null = null;
    if (atNorthTerminal) {
      busGoingSouth = true;
    } else if (atSouthTerminal) {
      busGoingSouth = false;
    } else if (hasMoved) {
      busGoingSouth = vec.dLat + vec.dLng < 0;
    }

    if (hasValidTrip && busGoingSouth !== null && busGoingSouth !== passengerGoingSouth) {
      const oppositeLabel = busGoingSouth ? 'Heading to Cabanatuan' : 'Heading to Bongabon';
      return {
        priority: 3,
        badge: `Opposite Way (${oppositeLabel} • ${dist.toFixed(1)} km away)`,
      };
    }

    if (dist <= 0.18) {
      return {
        priority: 0,
        badge: `Arrived at ${origin.stop_name} now!`,
      };
    }

    const busPosScore = curLat + curLng;
    const stopPosScore = stopLat + stopLng;
    const busPassedGoingSouth = passengerGoingSouth && busPosScore < stopPosScore - 0.002;
    const busPassedGoingNorth = !passengerGoingSouth && busPosScore > stopPosScore + 0.002;

    if (hasValidTrip && (busPassedGoingSouth || busPassedGoingNorth)) {
      return {
        priority: 2,
        badge: `Missed Bus (${dist.toFixed(1)} km past your stop)`,
      };
    }

    const liveSpeedKmh = vec && vec.speedKmh >= 5 ? vec.speedKmh : 28.0;
    const mins = Math.max(1, Math.round((dist / liveSpeedKmh) * 60));
    return {
      priority: 1,
      badge: `Arriving in ~${mins} mins (${dist.toFixed(1)} km away)`,
    };
  }

  computeEtaBadge(b: any): string {
    return this.getBusStatusInfo(b).badge;
  }

  getTopRibbonLabel(b: any): string {
    const priority = this.getBusStatusInfo(b).priority;
    if (priority === 3) {
      return 'ALL BUSES CURRENTLY HEADING OPPOSITE WAY';
    }
    if (priority === 2) {
      return 'NO APPROACHING BUS — NEXT LOOP';
    }
    return 'NEXT MINI-BUS FOR YOUR LOCATION';
  }

  getSortedBuses(): any[] {
    if (!this.buses) return [];
    const origin = this.getActiveOrigin();
    if (!origin) return this.buses;

    const stopLat = Number(origin.lat);
    const stopLng = Number(origin.lng);

    return [...this.buses].sort((a, b) => {
      const priorityA = this.getBusStatusInfo(a).priority;
      const priorityB = this.getBusStatusInfo(b).priority;

      if (priorityA !== priorityB) {
        return priorityA - priorityB;
      }

      const distA = this.haversineKm(Number(a.lat), Number(a.lng), stopLat, stopLng);
      const distB = this.haversineKm(Number(b.lat), Number(b.lng), stopLat, stopLng);
      return distA - distB;
    });
  }

  async submitFeedback(): Promise<void> {
    this.fbStatus = '';
    this.fbError = '';
    if (!this.fbMessage.trim()) return;

    try {
      const res = await fetch(`${this.serverUrl}/api/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          bus_id: this.fbBusId,
          user_id: this.loggedInUser?.user_id || null,
          passenger_name: this.loggedInUser?.full_name || 'Commuter',
          category: this.fbCategory,
          message: this.fbMessage.trim(),
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        this.fbError = data.detail || 'Could not send your report. Please try again.';
        this.cdr.detectChanges();
        return;
      }
      this.fbMessage = '';
      this.fbStatus = 'Thank you! Your report was sent to the Cooperative Dispatcher.';
      this.cdr.detectChanges();
    } catch {
      this.fbError = `Cannot connect to ${this.serverUrl}. Please check your connection and try again.`;
      this.cdr.detectChanges();
    }
  }
}