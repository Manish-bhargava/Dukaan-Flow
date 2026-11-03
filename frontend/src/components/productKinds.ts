/** Which illustrated pack (ProductArt) to draw for a category. */
export type ArtKind = 'biscuits' | 'homecare' | 'tea' | 'noodles' | 'snacks' | 'staples' | 'personal' | 'beverages' | 'carton'

const BY_CATEGORY: Record<string, ArtKind> = {
  biscuits: 'biscuits',
  'home care': 'homecare',
  tea: 'tea',
  noodles: 'noodles',
  snacks: 'snacks',
  staples: 'staples',
  'personal care': 'personal',
  beverages: 'beverages',
}

export const artForCategory = (name: string): ArtKind => BY_CATEGORY[name.trim().toLowerCase()] ?? 'carton'
