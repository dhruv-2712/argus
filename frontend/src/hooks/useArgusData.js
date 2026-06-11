import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { api } from "../api/client"

export function useAOIs() {
  return useQuery({ queryKey: ["aois"], queryFn: api.listAOIs, refetchInterval: 120000 })
}

export function useContacts(filters) {
  return useQuery({
    queryKey: ["contacts", filters],
    queryFn: () => api.getContacts(filters),
    enabled: true,
    refetchInterval: 60000,
  })
}

export function useDeleteAOI() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id) => api.deleteAOI(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["aois"] })
      qc.invalidateQueries({ queryKey: ["contacts"] })
    },
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
    onSuccess: (_data, { contactId }) => {
      qc.invalidateQueries({ queryKey: ["contacts"] })
      // Refetch the dossier so the persisted SPECTER analysis appears.
      qc.invalidateQueries({ queryKey: ["contact", contactId] })
    },
  })
}

export function useGenerateReport() {
  return useMutation({ mutationFn: (id) => api.generateReport(id) })
}

export function useRegional() {
  return useQuery({ queryKey: ["regional"], queryFn: api.getRegional, refetchInterval: 60000 })
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
