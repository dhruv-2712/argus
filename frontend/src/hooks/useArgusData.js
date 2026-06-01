import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../api/client"

export function useAOIs() {
  return useQuery({ queryKey: ["aois"], queryFn: api.listAOIs, refetchInterval: 60000 })
}

export function useContacts(filters) {
  return useQuery({
    queryKey: ["contacts", filters],
    queryFn: () => api.getContacts(filters),
    enabled: true,
    refetchInterval: 30000,
  })
}

export function useScan() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, layers }) => api.scanAOI(id, layers),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["contacts"] })
      qc.invalidateQueries({ queryKey: ["aois"] })
    },
  })
}

export function useCreateAOI() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.createAOI,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["aois"] }),
  })
}

export function useSimulate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ aoiId, contactId }) => api.simulate(aoiId, contactId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["contacts"] }),
  })
}

export function useGenerateReport() {
  return useMutation({ mutationFn: (id) => api.generateReport(id) })
}

export function useRegional() {
  return useQuery({ queryKey: ["regional"], queryFn: api.getRegional, refetchInterval: 30000 })
}

export function useTracks(aoiId) {
  return useQuery({
    queryKey: ["tracks", aoiId],
    queryFn: () => api.getTracks(aoiId),
    enabled: !!aoiId,
    refetchInterval: 30000,
  })
}

export function useContactDetail(contactId) {
  return useQuery({
    queryKey: ["contact", contactId],
    queryFn: () => api.getContact(contactId),
    enabled: !!contactId,
  })
}

export function useTerrain(contact) {
  const lat = contact?.lat
  const lon = contact?.lon
  return useQuery({
    queryKey: ["terrain", lat, lon],
    queryFn: () => api.getTerrain(lat, lon),
    enabled: lat != null && lon != null,
    staleTime: 60 * 60 * 1000,
    retry: 1,
  })
}
