import { Fragment, useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, useMap } from 'react-leaflet';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { EngineerRouteLayer } from './EngineerRouteLayer';
import { TicketMarker } from './TicketMarker';
import { EngineerStartMarker } from './EngineerStartMarker';
import { getEngineerColor } from '@/lib/colors';
import { useUiStore } from '@/store/useUiStore';
import { URGENT_PRIORITY, type DonePlan, type EngineerRoster, type TicketSummary } from '@/types/domain';

interface Props {
  plan: DonePlan;
  roster: EngineerRoster[];
  tickets: TicketSummary[];
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 0) return;
    // Auto-center on the plan's bounding box on first load.
    map.fitBounds(L.latLngBounds(points), { padding: [32, 32] });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points.length]);
  return null;
}

export function MapView({ plan, roster, tickets }: Props) {
  const highlightedEngineerId = useUiStore((s) => s.highlightedEngineerId);
  const toggleHighlightedEngineer = useUiStore((s) => s.toggleHighlightedEngineer);
  const openTicket = useUiStore((s) => s.openTicket);

  const rosterById = useMemo(() => new Map(roster.map((r) => [r.engineerId, r])), [roster]);
  const ticketById = useMemo(() => new Map(tickets.map((t) => [t.ticketId, t])), [tickets]);

  const diffTicketIds = useMemo(() => {
    if (!plan.diff) return new Set<number>();
    return new Set([
      ...plan.diff.newlyAssigned,
      ...plan.diff.changedAssignments.map((c) => c.ticketId)
    ]);
  }, [plan.diff]);

  const diffEngineerIds = useMemo(() => {
    if (!plan.diff) return new Set<number>();
    const ids = new Set<number>();
    plan.diff.changedAssignments.forEach((c) => {
      if (c.afterEngineerId !== undefined) ids.add(c.afterEngineerId);
    });
    return ids;
  }, [plan.diff]);

  const allPoints: [number, number][] = [];

  const engineerLayers = plan.engineers.map((engineer) => {
    const info = rosterById.get(engineer.engineerId);
    const color = getEngineerColor(engineer.engineerId);
    const selected = highlightedEngineerId === engineer.engineerId;
    const dimmed = highlightedEngineerId !== null && !selected;

    const stopPositions: [number, number][] = [];
    const markers = [...engineer.route]
      .sort((a, b) => a.sequenceNo - b.sequenceNo)
      .map((stop) => {
        const ticket = ticketById.get(stop.ticketId);
        if (!ticket || ticket.lat === null || ticket.lon === null) return null;
        const position: [number, number] = [ticket.lat, ticket.lon];
        stopPositions.push(position);
        allPoints.push(position);
        return (
          <TicketMarker
            key={stop.ticketId}
            position={position}
            color={color}
            urgent={ticket.priority === URGENT_PRIORITY}
            emergency={ticket.requiredSkill === 'emergency'}
            unassigned={false}
            diffHighlight={diffTicketIds.has(stop.ticketId)}
            opacity={dimmed ? 0.3 : 1}
            onClick={() => openTicket(stop.ticketId)}
          />
        );
      });

    if (info) {
      allPoints.push([info.startLat, info.startLon]);
    }

    return {
      engineerId: engineer.engineerId,
      color,
      markers,
      polylinePositions: info ? ([[info.startLat, info.startLon], ...stopPositions] as [number, number][]) : [],
      selected,
      dimmed,
      diffActive: diffEngineerIds.has(engineer.engineerId)
    };
  });

  const officePositions = useMemo(() => {
    const seen = new Set<string>();
    const points: [number, number][] = [];
    roster.forEach((r) => {
      const key = `${r.startLat},${r.startLon}`;
      if (!seen.has(key)) {
        seen.add(key);
        points.push([r.startLat, r.startLon]);
      }
    });
    return points;
  }, [roster]);

  const unassignedMarkers = plan.unassigned
    .map((u) => {
      const ticket = ticketById.get(u.ticketId);
      if (!ticket || ticket.lat === null || ticket.lon === null) return null;
      const position: [number, number] = [ticket.lat, ticket.lon];
      allPoints.push(position);
      return (
        <TicketMarker
          key={u.ticketId}
          position={position}
          color="#9AA0AA"
          urgent={ticket.priority === URGENT_PRIORITY}
          emergency={false}
          unassigned
          onClick={() => openTicket(u.ticketId)}
        />
      );
    })
    .filter(Boolean);

  return (
    <MapContainer
      center={[55.75, 37.6]}
      zoom={11}
      style={{ width: '100%', height: '100%' }}
      // TicketMarker/EngineerRouteLayer already carry priority/status via
      // ring + icon + color, so clicking a route highlights its EngineerCard
      // without needing a separate control here.
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds points={allPoints} />
      {officePositions.map((pos) => (
        <EngineerStartMarker key={pos.join(',')} position={pos} />
      ))}
      {engineerLayers.map((layer) => (
        <Fragment key={layer.engineerId}>
          <EngineerRouteLayer
            positions={layer.polylinePositions}
            color={layer.color}
            selected={layer.selected}
            dimmed={layer.dimmed}
            diffActive={layer.diffActive}
            onClick={() => toggleHighlightedEngineer(layer.engineerId)}
          />
          {layer.markers}
        </Fragment>
      ))}
      {unassignedMarkers}
    </MapContainer>
  );
}
