# ACC Tool Evaluation Report — Test Models

Generated: 2026-03-25T06:28:00.681422
Models: 4351, digital_hub, samuel_macalister_sample_house, wbdg_office

## Global Summary
| Metric | Value |
|--------|-------|
| F1 (aggregated) | **0.475** |
| Precision | 0.412 |
| Recall | 0.562 |
| TP / FP / FN | 168 / 240 / 131 |

## Per-Rule Summary
| Rule | F1 | Precision | Recall | TP | FP | FN |
|------|---:|----------:|-------:|---:|---:|---:|
| 304_3_1_circular_space | 1.000 | 1.000 | 1.000 | 2 | 0 | 0 |
| 305_3_size | 0.000 | 0.000 | 0.000 | 0 | 7 | 1 |
| 404_2_5_two_doors_in_series | 0.000 | 0.000 | 0.000 | 0 | 46 | 1 |
| 504_2_non_uniform_risers_treads | 0.000 | 0.000 | 0.000 | 0 | 1 | 0 |
| 504_2_riser_height | 0.051 | 0.029 | 0.250 | 1 | 34 | 3 |
| 504_2_stair_slab_connection | 0.571 | 1.000 | 0.400 | 2 | 0 | 3 |
| 504_2_tread_length | 0.667 | 0.500 | 1.000 | 2 | 2 | 0 |
| clearance_front_of_doors | 0.154 | 0.090 | 0.545 | 6 | 61 | 5 |
| doors_and_windows | 0.250 | 0.143 | 1.000 | 2 | 12 | 0 |
| large_spaces_more_than_one_door | 0.267 | 0.800 | 0.160 | 4 | 1 | 21 |
| slab_thickness | 0.000 | 0.000 | 0.000 | 0 | 0 | 3 |
| slabs_guarded_against_falling | 0.052 | 0.118 | 0.033 | 2 | 15 | 58 |
| space_validation_inside | 0.300 | 1.000 | 0.176 | 3 | 0 | 14 |
| space_validation_intersect | 0.444 | 0.294 | 0.909 | 20 | 48 | 2 |
| spaces_same_storey_same_bottom_elevation | 1.000 | 1.000 | 1.000 | 124 | 0 | 0 |
| unallocated_areas | 0.000 | 0.000 | 0.000 | 0 | 13 | 20 |

## Detailed Error Analysis

### 304_3_1_circular_space — F1=1.000 (PERFECT)
No errors on test models.

### 305_3_size — F1=0.000

**4351**: PASS (TP=0)
**digital_hub**: PASS (TP=0)
**samuel_macalister_sample_house**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=5 FN=1
  - **False Positives** (predicted but not expected): 5 GUIDs
    - `{'guid': '1N_4TwOEH5194SbNmRTFml', 'type': 'IfcFurniture'}`
    - `{'guid': '1mNYMX4dvDThNrJdPk$s13', 'type': 'IfcFurniture'}`
    - `{'guid': '1mNYMX4dvDThNrJdPk$si3', 'type': 'IfcFurniture'}`
    - `{'guid': '29jzdd0Ab5sOIOupfzxDfN', 'type': 'IfcFurniture'}`
    - `{'guid': '2PbrheIID1GfgGRPO3yx$6', 'type': 'IfcFurniture'}`
  - **False Negatives** (expected but missed): 1 GUIDs
    - **Space.2.8 : Master Bedroom[206]**: 305.3 Size
Space.2.8 : Master Bedroom[206] has inaccessible areas.
      - `{'guid': '0lntrd6l1AGwfcnKJK5r3q', 'type': 'IfcWall'}`

**wbdg_office**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=2 FN=0
  - **False Positives** (predicted but not expected): 2 GUIDs
    - `{'guid': '2$Ac70E451LvAGNHpGKDfo', 'type': 'IfcFurnishingElement'}`
    - `{'guid': '2$Ac70E451LvAGNHpGKDt5', 'type': 'IfcFurnishingElement'}`


### 404_2_5_two_doors_in_series — F1=0.000

**4351**: PASS (TP=0)
**digital_hub**: PASS (TP=0)
**samuel_macalister_sample_house**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=0 FN=1
  - **False Negatives** (expected but missed): 1 GUIDs
    - **Door.0.2 And Door.0.3**: 404.2.5 Two Doors in Series
Distance between doors is 1.16 m. The minimum distance is 1.22 m.
      - `{'guid': '3ch3OBgkrCEw4mDhJ2eOWH', 'type': 'IfcSpace'}`

**wbdg_office**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=46 FN=0
  - **False Positives** (predicted but not expected): 46 GUIDs
    - `{'guid': '06njXbG3HC4RydTXssDq$e', 'type': 'IfcDoor'}`
    - `{'guid': '0YUzX040H3bhUyeerRS91$', 'type': 'IfcDoor'}`
    - `{'guid': '1B_elmwz51ieqPd_MO2yZ0', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_$4', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_0z', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_1D', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_1e', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_3s', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_4u', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_Gm', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_kO', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_rV', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_vQ', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_ws', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_yp', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_zR', 'type': 'IfcDoor'}`
    - `{'guid': '1h7qyFpbf0qggP_pQnt_zc', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77u0o', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77u2P', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77u2e', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77u3r', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77u5A', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77wwb', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77x0R', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77x1u', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77x7o', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77x9N', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xAg', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xCp', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xD6', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xDb', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xEd', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xF_', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xGO', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xGt', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xH0', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xJp', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xKn', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xNK', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xUv', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xVs', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xaz', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xnt', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xsW', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xwP', 'type': 'IfcDoor'}`
    - `{'guid': '3If4otxpvBjO9DSa$bK$uj', 'type': 'IfcDoor'}`


### 504_2_non_uniform_risers_treads — F1=0.000

**4351**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=1 FN=0
  - **False Positives** (predicted but not expected): 1 GUIDs
    - `{'guid': '2yrvjJLF5DO99bzmxJnJrl', 'type': 'IfcStair'}`

**digital_hub**: PASS (TP=0)
**samuel_macalister_sample_house**: PASS (TP=0)
**wbdg_office**: PASS (TP=0)

### 504_2_riser_height — F1=0.051

**4351**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=17 FN=0
  - **False Positives** (predicted but not expected): 17 GUIDs
    - `{'guid': '05IUfpHsL9BgFcXObHJJxD', 'type': 'IfcMember'}`
    - `{'guid': '0F8IyAXCD7S9i7ZjXP77iP', 'type': 'IfcMember'}`
    - `{'guid': '0QunSioVvB2xY3ux28I6JO', 'type': 'IfcMember'}`
    - `{'guid': '0zm_RkrLH2tRithg6zqFH2', 'type': 'IfcRailing'}`
    - `{'guid': '0zm_RkrLH2tRithg6zqFHE', 'type': 'IfcRailing'}`
    - `{'guid': '0zm_RkrLH2tRithg6zqFIz', 'type': 'IfcStair'}`
    - `{'guid': '1AMAMzZITBfejW_xu2IBK7', 'type': 'IfcRailing'}`
    - `{'guid': '1AMAMzZITBfejW_xu2IBKB', 'type': 'IfcRailing'}`
    - `{'guid': '1AMAMzZITBfejW_xu2IBMi', 'type': 'IfcStair'}`
    - `{'guid': '1AUHUgTAH1ZPnbMDxS_z8d', 'type': 'IfcStairFlight'}`
    - `{'guid': '1RuZ0BfEf5qvvxOl1$DCmW', 'type': 'IfcStair'}`
    - `{'guid': '1rJwPna6j36Ryf9BeRhyi1', 'type': 'IfcSlab'}`
    - `{'guid': '2ggG7xSg5EB8p5NZA9Vthc', 'type': 'IfcMember'}`
    - `{'guid': '2t7Cp302P04g8y50Ws9Abn', 'type': 'IfcStairFlight'}`
    - `{'guid': '2yrvjJLF5DO99bzmxJnJos', 'type': 'IfcRailing'}`
    - `{'guid': '2yrvjJLF5DO99bzmxJnJrl', 'type': 'IfcStair'}`
    - `{'guid': '3GUUpM0_TFyOHeW8WSUinC', 'type': 'IfcStairFlight'}`

**digital_hub**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=8 FN=3
  - **False Positives** (predicted but not expected): 8 GUIDs
    - `{'guid': '0YVU7tDBX86u6UVVsSmdw5', 'type': 'IfcStairFlight'}`
    - `{'guid': '0YVU7tDBX86u6UVVsSmdwA', 'type': 'IfcStairFlight'}`
    - `{'guid': '0YVU7tDBX86u6UVVsSmdxt', 'type': 'IfcStairFlight'}`
    - `{'guid': '0YVU7tDBX86u6UVVsSmdxy', 'type': 'IfcStairFlight'}`
    - `{'guid': '3LF03GdXv2GhSTK1xTZzXJ', 'type': 'IfcStairFlight'}`
    - `{'guid': '3LF03GdXv2GhSTK1xTZzXK', 'type': 'IfcStairFlight'}`
    - `{'guid': '3LF03GdXv2GhSTK1xTZzXZ', 'type': 'IfcStairFlight'}`
    - `{'guid': '3LF03GdXv2GhSTK1xTZzXa', 'type': 'IfcStairFlight'}`
  - **False Negatives** (expected but missed): 3 GUIDs
    - **Stair.-2.1: 329 Mm**: 504.2 Treads and Risers
Stair Stair.-2.1 has steps at the beginning that are non-uniform. Riser height at beginning is 0.33 m and elsewhere 0.18 m.
      - `{'guid': '0YVU7tDBX86u6UVVsSmdx$', 'type': 'IfcStair'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49deXD', 'type': 'IfcSlab'}`
    - **Stair.-2.2: 329 Mm**: 504.2 Treads and Risers
Stair Stair.-2.2 has steps at the beginning that are non-uniform. Riser height at beginning is 0.33 m and elsewhere 0.18 m.
      - `{'guid': '23Np8uMAvEN9H6Ds49deXD', 'type': 'IfcSlab'}`
      - `{'guid': '3LF03GdXv2GhSTK1xTZzXx', 'type': 'IfcStair'}`

**samuel_macalister_sample_house**: F1=0.18 | P=0.10 R=1.00 | TP=1 FP=9 FN=0
  - **False Positives** (predicted but not expected): 9 GUIDs
    - `{'guid': '07dHKEjXj6kwcHAxpyAkHd', 'type': 'IfcStairFlight'}`
    - `{'guid': '07dHKEjXj6kwcHAxpyAkMS', 'type': 'IfcStair'}`
    - `{'guid': '0H7vgQcNjEo8efFHzwVqPR', 'type': 'IfcRailing'}`
    - `{'guid': '1N_4TwOEH5194SbNmRTDH0', 'type': 'IfcSlab'}`
    - `{'guid': '1N_4TwOEH5194SbNmRTDNX', 'type': 'IfcStair'}`
    - `{'guid': '1N_4TwOEH5194SbNmRTDNY', 'type': 'IfcStairFlight'}`
    - `{'guid': '1SDKa3RCzEzvwMoVlm1Auv', 'type': 'IfcRailing'}`
    - `{'guid': '2ZlFFrvcbDavSm_g3LjLIb', 'type': 'IfcStairFlight'}`
    - `{'guid': '2ZlFFrvcbDavSm_g3LjLiI', 'type': 'IfcRailing'}`

**wbdg_office**: PASS (TP=0)

### 504_2_stair_slab_connection — F1=0.571

**4351**: PASS (TP=0)
**digital_hub**: PASS (TP=0)
**samuel_macalister_sample_house**: PASS (TP=0)
**wbdg_office**: F1=0.57 | P=1.00 R=0.40 | TP=2 FP=0 FN=3
  - **False Negatives** (expected but missed): 3 GUIDs
    - **Stair.0.1**: 504.2 Treads and Risers
Stair Stair.0.1 is not connected to slabs at the end. Slab might be missing.
      - `{'guid': '1Cckmc_QjEFAHHQ3e8qDFi', 'type': 'IfcSlab'}`
    - **Stair.0.2**: 504.2 Treads and Risers
Stair Stair.0.2 is not connected to slabs at the end. Slab might be missing.
      - `{'guid': '27dLDsxMX8Sv5rKurGZypo', 'type': 'IfcRailing'}`
      - `{'guid': '37hauuzqP2MBAzwN0mWNjY', 'type': 'IfcSlab'}`


### 504_2_tread_length — F1=0.667

**4351**: PASS (TP=0)
**digital_hub**: F1=0.67 | P=0.50 R=1.00 | TP=2 FP=2 FN=0
  - **False Positives** (predicted but not expected): 2 GUIDs
    - `{'guid': '0YVU7tDBX86u6UVVsSmdx$', 'type': 'IfcStair'}`
    - `{'guid': '3LF03GdXv2GhSTK1xTZzXx', 'type': 'IfcStair'}`

**samuel_macalister_sample_house**: PASS (TP=0)
**wbdg_office**: PASS (TP=0)

### clearance_front_of_doors — F1=0.154

**4351**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=1 FN=2
  - **False Positives** (predicted but not expected): 1 GUIDs
    - `{'guid': '2rY6ZB_FT3bRLgI3yFLRkp', 'type': 'IfcDoor'}`
  - **False Negatives** (expected but missed): 2 GUIDs
    - **Slab.2.1 Too Close To Door.1.1 Component**: Clearance in Front of Doors
- Component Slab.2.1 intersects the required free area with dimensions 1.07 m and 0.15 m.
      - `{'guid': '0S4TGKDX5FsvETM2lopwZJ', 'type': 'IfcSlab'}`
    - **Wall.2.8 Too Close To Door.2.2 Component**: Clearance in Front of Doors
- Component Wall.2.8 intersects the required free area with dimensions 0.07 m and 0.05 m.
      - `{'guid': '3aFPed1ijDewmDm14mfR5G', 'type': 'IfcWallStandardCase'}`

**digital_hub**: F1=0.17 | P=0.09 R=1.00 | TP=6 FP=58 FN=0
  - **False Positives** (predicted but not expected): 58 GUIDs
    - `{'guid': '03fYK2KZb9bQXMSPptFYJv', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFYK6', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFYLQ', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFYNK', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFYOs', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFYPu', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFYQ4', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFYRK', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFYV5', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFYf$', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFYku', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFYlU', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFYlo', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFZay', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFZbq', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFZdK', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFZdo', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFZeI', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFZf8', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFZgm', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFZhc', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFZkk', 'type': 'IfcDoor'}`
    - `{'guid': '03fYK2KZb9bQXMSPptFZlI', 'type': 'IfcDoor'}`
    - `{'guid': '0YVU7tDBX86u6UVVsSmdwk', 'type': 'IfcDoor'}`
    - `{'guid': '0ehNcYPbH3JQicvZQLHO$q', 'type': 'IfcDoor'}`
    - `{'guid': '0ehNcYPbH3JQicvZQLHOvk', 'type': 'IfcDoor'}`
    - `{'guid': '11eI7IJI9EJgsn80j11Erx', 'type': 'IfcDoor'}`
    - `{'guid': '1oTOc$LbLC8Ob8HP$$4q0L', 'type': 'IfcDoor'}`
    - `{'guid': '1oTOc$LbLC8Ob8HP$$4q0n', 'type': 'IfcDoor'}`
    - `{'guid': '1oTOc$LbLC8Ob8HP$$4q13', 'type': 'IfcDoor'}`
    - `{'guid': '1oTOc$LbLC8Ob8HP$$4q2x', 'type': 'IfcDoor'}`
    - `{'guid': '1oTOc$LbLC8Ob8HP$$4q33', 'type': 'IfcDoor'}`
    - `{'guid': '1oTOc$LbLC8Ob8HP$$4q6s', 'type': 'IfcDoor'}`
    - `{'guid': '1oTOc$LbLC8Ob8HP$$4q7Q', 'type': 'IfcDoor'}`
    - `{'guid': '1oTOc$LbLC8Ob8HP$$4q7y', 'type': 'IfcDoor'}`
    - `{'guid': '1oTOc$LbLC8Ob8HP$$4qvE', 'type': 'IfcDoor'}`
    - `{'guid': '279opIq2rEtREtELGBVxB4', 'type': 'IfcDoor'}`
    - `{'guid': '279opIq2rEtREtELGBVxCY', 'type': 'IfcDoor'}`
    - `{'guid': '279opIq2rEtREtELGBVxDe', 'type': 'IfcDoor'}`
    - `{'guid': '279opIq2rEtREtELGBVxHB', 'type': 'IfcDoor'}`
    - `{'guid': '279opIq2rEtREtELGBVxHq', 'type': 'IfcDoor'}`
    - `{'guid': '279opIq2rEtREtELGBVxTT', 'type': 'IfcDoor'}`
    - `{'guid': '279opIq2rEtREtELGBVxUT', 'type': 'IfcDoor'}`
    - `{'guid': '279opIq2rEtREtELGBVxqA', 'type': 'IfcDoor'}`
    - `{'guid': '3A8hY1UoD7JhnLeZeDyU3l', 'type': 'IfcDoor'}`
    - `{'guid': '3LF03GdXv2GhSTK1xTZzXE', 'type': 'IfcDoor'}`
    - `{'guid': '3LJODRGPbDdfXHXShFL8Do', 'type': 'IfcDoor'}`
    - `{'guid': '3LJODRGPbDdfXHXShFL8H6', 'type': 'IfcDoor'}`
    - `{'guid': '3LJODRGPbDdfXHXShFL8OS', 'type': 'IfcDoor'}`
    - `{'guid': '3LJODRGPbDdfXHXShFL8TR', 'type': 'IfcDoor'}`
    - `{'guid': '3LJODRGPbDdfXHXShFL8Tj', 'type': 'IfcDoor'}`
    - `{'guid': '3LJODRGPbDdfXHXShFL8U8', 'type': 'IfcDoor'}`
    - `{'guid': '3LJODRGPbDdfXHXShFL8Ua', 'type': 'IfcDoor'}`
    - `{'guid': '3LJODRGPbDdfXHXShFL8Z2', 'type': 'IfcDoor'}`
    - `{'guid': '3LJODRGPbDdfXHXShFL8bJ', 'type': 'IfcDoor'}`
    - `{'guid': '3LJODRGPbDdfXHXShFLBss', 'type': 'IfcDoor'}`
    - `{'guid': '3LJODRGPbDdfXHXShFLBtN', 'type': 'IfcDoor'}`
    - `{'guid': '3LJODRGPbDdfXHXShFLBtR', 'type': 'IfcDoor'}`

**samuel_macalister_sample_house**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=0 FN=2
  - **False Negatives** (expected but missed): 2 GUIDs
    - **Wall.2.30 Too Close To Door.2.1 Component**: Clearance in Front of Doors
- Component Wall.2.30 intersects the required free area with dimensions 0.85 m and 0.12 m.
      - `{'guid': '2wm6PO6TX9IxXwLP21HySo', 'type': 'IfcDoor'}`
    - **Wall.2.30 Too Close To Door.2.2 Component**: Clearance in Front of Doors
- Component Wall.2.30 intersects the required free area with dimensions 0.85 m and 0.12 m.
      - `{'guid': '2wm6PO6TX9IxXwLP21HyWr', 'type': 'IfcDoor'}`

**wbdg_office**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=2 FN=1
  - **False Positives** (predicted but not expected): 2 GUIDs
    - `{'guid': '1h7qyFpbf0qggP_pQnt_66', 'type': 'IfcDoor'}`
    - `{'guid': '2N3oFtM8X6lO2dN1$77xjY', 'type': 'IfcDoor'}`
  - **False Negatives** (expected but missed): 1 GUIDs
    - **Sanitary Terminal.0.33.2 Too Close To Door.0.18 Component**: Clearance in Front of Doors
- Component Sanitary Terminal.0.33.2 intersects the required free area with dimensions 0.16 m and 0.02 m.
      - `{'guid': '0zG59wlnT37e_nm5jeqGJp', 'type': 'IfcFlowTerminal'}`


### doors_and_windows — F1=0.250

**4351**: F1=0.50 | P=0.33 R=1.00 | TP=2 FP=4 FN=0
  - **False Positives** (predicted but not expected): 4 GUIDs
    - `{'guid': '1Vp_ZIf01ANQz9mYpe1Peb', 'type': 'IfcDoor'}`
    - `{'guid': '2SqDm2VurA4wpcRwks3Xlh', 'type': 'IfcDoor'}`
    - `{'guid': '2gTG8I4eL6z9beKMqLBe0M', 'type': 'IfcDoor'}`
    - `{'guid': '2gTG8I4eL6z9beKMqLBe0q', 'type': 'IfcDoor'}`

**digital_hub**: PASS (TP=0)
**samuel_macalister_sample_house**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=8 FN=0
  - **False Positives** (predicted but not expected): 8 GUIDs
    - `{'guid': '20nhVaBTTAJguMI9o6oBQ8', 'type': 'IfcWindow'}`
    - `{'guid': '20nhVaBTTAJguMI9o6oBQ9', 'type': 'IfcWindow'}`
    - `{'guid': '20nhVaBTTAJguMI9o6oBQE', 'type': 'IfcWindow'}`
    - `{'guid': '20nhVaBTTAJguMI9o6oBQF', 'type': 'IfcWindow'}`
    - `{'guid': '20nhVaBTTAJguMI9o6oD2l', 'type': 'IfcWindow'}`
    - `{'guid': '20nhVaBTTAJguMI9o6oD4T', 'type': 'IfcWindow'}`
    - `{'guid': '20nhVaBTTAJguMI9o6oD5Q', 'type': 'IfcWindow'}`
    - `{'guid': '20nhVaBTTAJguMI9o6oDQ8', 'type': 'IfcWindow'}`

**wbdg_office**: PASS (TP=0)

### large_spaces_more_than_one_door — F1=0.267

**4351**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=0 FN=3
  - **False Negatives** (expected but missed): 3 GUIDs
    - **Space.0.2 : 1st Floor[4]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '2tMe7qG7n4XhDG_TV6Qihi', 'type': 'IfcSpace'}`
    - **Space.1.1 : 2nd Floor[5]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '2tMe7qG7n4XhDG_TV6Qihs', 'type': 'IfcSpace'}`
    - **Space.2.1 : 3rd Floor[8]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '2tMe7qG7n4XhDG_TV6Qihy', 'type': 'IfcSpace'}`

**digital_hub**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=0 FN=11
  - **False Negatives** (expected but missed): 11 GUIDs
    - **Space.-1.1 : Vr/ar Lab[1-11]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '3DCde23Rb8uBrhrJgjcLQ2', 'type': 'IfcSpace'}`
    - **Space.-1.10 : Eingangsbereich / Flur[1-1]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '3DCde23Rb8uBrhrJgjcLQU', 'type': 'IfcSpace'}`
    - **Space.-1.12 : Open Workspace Eg[1-7]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '3DCde23Rb8uBrhrJgjcLQ6', 'type': 'IfcSpace'}`
    - **Space.-1.2 : Veranstaltungsraum[1-12]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '3DCde23Rb8uBrhrJgjcLQ3', 'type': 'IfcSpace'}`
    - **Space.-1.5 : Cafeteria[1-2]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '3DCde23Rb8uBrhrJgjcLQ0', 'type': 'IfcSpace'}`
    - **Space.-2.4 : Flur - Ug[0-1]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '1aFRCtje92oh3_jKdNxTM3', 'type': 'IfcSpace'}`
    - **Space.-2.6 : Heizzentrale[0-5]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '1aFRCtje92oh3_jKdNxTMU', 'type': 'IfcSpace'}`
    - **Space.-2.9 : Rlt-raum[0-10]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '1aFRCtje92oh3_jKdNxTMQ', 'type': 'IfcSpace'}`
    - **Space.0.12 : Open Workspace 2[2-7]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '3DbdJyICv8GP1HEYzu7WjX', 'type': 'IfcSpace'}`
    - **Space.0.24 : Seminarraum Groß - Teilbar[2-17]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '3DbdJyICv8GP1HEYzu7Wje', 'type': 'IfcSpace'}`
    - **Space.0.5 : Flur - Og[2-1]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '3DbdJyICv8GP1HEYzu7WjQ', 'type': 'IfcSpace'}`

**samuel_macalister_sample_house**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=0 FN=2
  - **False Negatives** (expected but missed): 2 GUIDs
    - **Space.0.2 : Living[106]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '3ch3OBgkrCEw4mDhJ2eOZ3', 'type': 'IfcSpace'}`
    - **Space.0.4 : Kitchen & Dining[101]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '3ch3OBgkrCEw4mDhJ2eOci', 'type': 'IfcSpace'}`

**wbdg_office**: F1=0.57 | P=0.80 R=0.44 | TP=4 FP=1 FN=5
  - **False Positives** (predicted but not expected): 1 GUIDs
    - `{'guid': '06njXbG3HC4RydTXssDqXH', 'type': 'IfcSpace'}`
  - **False Negatives** (expected but missed): 5 GUIDs
    - **Space.0.13 : Scif Open Office[143]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '04Sq57eS5FffNezn2ilgC3', 'type': 'IfcSpace'}`
    - **Space.0.21 : Noc[158]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '04Sq57eS5FffNezn2ilg3k', 'type': 'IfcSpace'}`
    - **Space.0.5 : Boc[151]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '04Sq57eS5FffNezn2ilgCR', 'type': 'IfcSpace'}`
    - **Space.0.50 : Corridor[121]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '04Sq57eS5FffNezn2ilgtD', 'type': 'IfcSpace'}`
    - **Space.1.19 : Corridor[201]: Count (0) Of The Components Does Not Match The Requirement: ≥ 2**: Large Spaces Have to Have More than One Door
Count (0) of the components does not match the requirement: ≥ 2.
      - `{'guid': '06njXbG3HC4RydTXssDqYC', 'type': 'IfcSpace'}`


### slab_thickness — F1=0.000

**4351**: PASS (TP=0)
**digital_hub**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=0 FN=3
  - **False Negatives** (expected but missed): 3 GUIDs
    - **Wrong Value Of Property - Thickness: 0.00 M**: Slab Thickness
Slab component(s) have wrong value. The actual value of Property: Thickness is 0.00 m. ≥ 0.03 m.
      - `{'guid': '3A8hY1UoD7JhnLeZeDyU2J', 'type': 'IfcSlab'}`
    - **Wrong Value Of Property - Thickness: 0.00 M**: Slab Thickness
Slab component(s) have wrong value. The actual value of Property: Thickness is 0.00 m. ≥ 0.03 m.
      - `{'guid': '3LJODRGPbDdfXHXShFL93Z', 'type': 'IfcSlab'}`
      - `{'guid': '3LJODRGPbDdfXHXShFL9C6', 'type': 'IfcSlab'}`

**samuel_macalister_sample_house**: PASS (TP=0)
**wbdg_office**: PASS (TP=0)

### slabs_guarded_against_falling — F1=0.052

**4351**: F1=0.11 | P=0.50 R=0.06 | TP=1 FP=1 FN=15
  - **False Positives** (predicted but not expected): 1 GUIDs
    - `{'guid': '1rJwPna6j36Ryf9BeRhyi1', 'type': 'IfcSlab'}`
  - **False Negatives** (expected but missed): 15 GUIDs
    - **Slab.1.1**: Slabs must be Guarded against Falling
Slab.1.1 has barriers that are too low. The required height of a barrier is 1.00 m, and the height in the model is 0.91 m.
      - `{'guid': '1o6iSxmUv8P91r$iXVGWW4', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '2AIxs0u4bALRCp$bA8lTiR', 'type': 'IfcRailing'}`
      - `{'guid': '2yrvjJLF5DO99bzmxJnJrl', 'type': 'IfcStair'}`
    - **Slab.1.2**: Slabs must be Guarded against Falling
Slab.1.2 has barriers that are too low. The required height of a barrier is 1.00 m, and the height in the model is 0.91 m.
      - `{'guid': '05IUfpHsL9BgFcXObHJJxD', 'type': 'IfcMember'}`
      - `{'guid': '0QunSioVvB2xY3ux28I6JO', 'type': 'IfcMember'}`
      - `{'guid': '1AMAMzZITBfejW_xu2IBMi', 'type': 'IfcStair'}`
      - `{'guid': '1AMAMzZITBfejW_xu2IB_D', 'type': 'IfcRailing'}`
      - `{'guid': '2t7Cp302P04g8y50Ws9Abn', 'type': 'IfcStairFlight'}`
      - `{'guid': '3PaccedUL48Q9C0HOcrtmk', 'type': 'IfcRailing'}`
      - `{'guid': '3iAO9JyKfEt9Ta5BddcDnh', 'type': 'IfcSlab'}`
    - **Slab.2.1**: Slabs must be Guarded against Falling
Slab.2.1 has barriers that are too low. The required height of a barrier is 1.00 m, and the height in the model is 0.59 m.
      - `{'guid': '0S4TGKDX5FsvETM2lopwZJ', 'type': 'IfcSlab'}`
      - `{'guid': '0zm_RkrLH2tRithg6zqEqi', 'type': 'IfcRailing'}`
      - `{'guid': '0zm_RkrLH2tRithg6zqEsr', 'type': 'IfcRailing'}`
      - `{'guid': '0zm_RkrLH2tRithg6zqFIz', 'type': 'IfcStair'}`
      - `{'guid': '2rY6ZB_FT3bRLgI3yFLROE', 'type': 'IfcWall'}`

**digital_hub**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=4 FN=17
  - **False Positives** (predicted but not expected): 4 GUIDs
    - `{'guid': '0CWDnGbzX4Sf1BesL9TjKx', 'type': 'IfcSlab'}`
    - `{'guid': '0qHt$K$J1CDgKrHmzIgbUy', 'type': 'IfcSlab'}`
    - `{'guid': '3A8hY1UoD7JhnLeZeDyU2J', 'type': 'IfcSlab'}`
    - `{'guid': '3LJODRGPbDdfXHXShFL9C6', 'type': 'IfcSlab'}`
  - **False Negatives** (expected but missed): 17 GUIDs
    - **Slab.0.4**: Slabs must be Guarded against Falling
Slab.0.4 has barriers that are too low. The required height of a barrier is 1.00 m, and the height in the model is 0.50 m.
      - `{'guid': '12bPoIwbv0tBGfPfnvCUW2', 'type': 'IfcWall'}`
      - `{'guid': '12bPoIwbv0tBGfPfnvCUYu', 'type': 'IfcWall'}`
      - `{'guid': '12bPoIwbv0tBGfPfnvCUau', 'type': 'IfcWall'}`
      - `{'guid': '12bPoIwbv0tBGfPfnvCUc2', 'type': 'IfcWall'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49de1S', 'type': 'IfcWall'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49de3t', 'type': 'IfcWall'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49de4U', 'type': 'IfcWall'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49de77', 'type': 'IfcWall'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49dh$Z', 'type': 'IfcWall'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49dh_f', 'type': 'IfcWall'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49dhvA', 'type': 'IfcWall'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49dhvb', 'type': 'IfcWall'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49dhw1', 'type': 'IfcWall'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49dhxn', 'type': 'IfcWall'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49dhyz', 'type': 'IfcWall'}`
      - `{'guid': '23Np8uMAvEN9H6Ds49dhzi', 'type': 'IfcWall'}`
      - `{'guid': '3BmeJtEDj3AQO77Os2w6ld', 'type': 'IfcSlab'}`

**samuel_macalister_sample_house**: F1=0.06 | P=0.11 R=0.04 | TP=1 FP=8 FN=26
  - **False Positives** (predicted but not expected): 8 GUIDs
    - `{'guid': '0LKJKCHUL1kBtnlFXddz6a', 'type': 'IfcSlab'}`
    - `{'guid': '0PSFPzOkvFnf082fy0SVrB', 'type': 'IfcSlab'}`
    - `{'guid': '0WFFycJ9rEj9FbADAA0q3o', 'type': 'IfcSlab'}`
    - `{'guid': '1UXnAYut94jfvp2gf33JX9', 'type': 'IfcSlab'}`
    - `{'guid': '1UXnAYut94jfvp2gf33Js1', 'type': 'IfcSlab'}`
    - `{'guid': '1ypci01sD9aQpE0S$W9jFF', 'type': 'IfcSlab'}`
    - `{'guid': '3OLNF2_DL6hfPgh8Bw7fI7', 'type': 'IfcSlab'}`
    - `{'guid': '3Pf5WxDcT7yf4sAHDxknUs', 'type': 'IfcSlab'}`
  - **False Negatives** (expected but missed): 26 GUIDs
    - **Slab.0.3**: Slabs must be Guarded against Falling
Slab.0.3 has barriers that are too low. The required height of a barrier is 1.00 m, and the height in the model is 0.79 m.
      - `{'guid': '0H7vgQcNjEo8efFHzwVpwh', 'type': 'IfcBuildingElementProxy'}`
      - `{'guid': '1$p8tACJ938vr1_lKOJJ0t', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '1PDnLIM013wvkZO9Lb4$GV', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '1PDnLIM013wvkZO9Lb4$j_', 'type': 'IfcCurtainWall'}`
      - `{'guid': '1PDnLIM013wvkZO9Lb4$wc', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '1RUi90wQT3ihQ$96bMNGiu', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '1RUi90wQT3ihQ$96bMNGvH', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '1cCK8nA61FduUezO75i8dB', 'type': 'IfcSlab'}`
      - `{'guid': '1oPutv5ADAxgWEbAZbN6Wv', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '29jzdd0Ab5sOIOupfzx0h8', 'type': 'IfcBuildingElementProxy'}`
      - `{'guid': '29jzdd0Ab5sOIOupfzx1Ur', 'type': 'IfcBuildingElementProxy'}`
      - `{'guid': '29jzdd0Ab5sOIOupfzx2y0', 'type': 'IfcBuildingElementProxy'}`
      - `{'guid': '2OulbipBrAkwQNv_KJRUYY', 'type': 'IfcCurtainWall'}`
      - `{'guid': '2OulbipBrAkwQNv_KJRUgr', 'type': 'IfcCurtainWall'}`
      - `{'guid': '2ZlFFrvcbDavSm_g3LjLIb', 'type': 'IfcStairFlight'}`
      - `{'guid': '2ZlFFrvcbDavSm_g3LjLIe', 'type': 'IfcStair'}`
      - `{'guid': '2hD3j_DmLBXxhCCy1gOWVy', 'type': 'IfcCurtainWall'}`
      - `{'guid': '2pfAHb2EL46hq_sMVbImEh', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '38NblWsDL1I8DljLvn67Sd', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '3NtsDuzRb1WReLiDQX$2CA', 'type': 'IfcCurtainWall'}`
      - `{'guid': '3Yxgiuz3TDpeHhosGP5a_d', 'type': 'IfcColumn'}`
      - `{'guid': '3lLx0gNe59vvExhby0Bff1', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '3rPRxvVIT7WRZKOFIc3wXL', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '3vi8Xy_cHA1R$gUoZ0tZjz', 'type': 'IfcBuildingElementProxy'}`
    - **Slab.2.3**: Slabs must be Guarded against Falling
Slab.2.3 has adjacent landing components that are too far below. The maximum allowed drop is 0.50 m, and the height in the model is 1.20 m.
      - `{'guid': '38BWtPCUX0VgAKmmGnoLQm', 'type': 'IfcSlab'}`
      - `{'guid': '3lIj7B0LnBjf0mvxk2zve8', 'type': 'IfcSite'}`
    - **Slab.2.3**: Slabs must be Guarded against Falling
Slab.2.3 is missing a barrier/barriers.
      - `{'guid': '38BWtPCUX0VgAKmmGnoLQm', 'type': 'IfcSlab'}`

**wbdg_office**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=2 FN=0
  - **False Positives** (predicted but not expected): 2 GUIDs
    - `{'guid': '1Cckmc_QjEFAHHQ3e8qDFi', 'type': 'IfcSlab'}`
    - `{'guid': '37hauuzqP2MBAzwN0mWNjY', 'type': 'IfcSlab'}`


### space_validation_inside — F1=0.300

**4351**: PASS (TP=0)
**digital_hub**: F1=0.18 | P=1.00 R=0.10 | TP=1 FP=0 FN=9
  - **False Negatives** (expected but missed): 9 GUIDs
    - **Space.-1.22 : Treppenhaus West - Eg[1-19]**: Space Validation
- Components Slab.-1.1.1 are inside the space.
- Space intersects with Slab.-1.2 and Slab.0.5. The intersection area is 16.34 m2.
      - `{'guid': '3DCde23Rb8uBrhrJgjcLQr', 'type': 'IfcSpace'}`
    - **Space.-1.19 : Treppenhaus Ost - Eg[1-17]**: Space Validation
- Components Slab.-1.2.1 are inside the space.
- Space intersects with Slab.-1.1 and Slab.0.5. The intersection area is 16.34 m2.
      - `{'guid': '3DCde23Rb8uBrhrJgjcLQE', 'type': 'IfcSpace'}`
    - **Space.-1.10 : Eingangsbereich / Flur[1-1]**: Space Validation
- Components Slab.-1.3.1 are inside the space.
- Space intersects with Slab.0.5 and Wall.-1.61. The intersection area is 458.92 m2.
- Space perimeter is not totally aligned with bound
      - `{'guid': '3DCde23Rb8uBrhrJgjcLQU', 'type': 'IfcSpace'}`
    - **Space.-2.10 : Treppenhaus West - Ug[0-12]**: Space Validation
- Components Slab.-2.1.1 are inside the space.
- Space intersects with Slab.-1.5. The intersection area is 8.98 m2.
      - `{'guid': '1aFRCtje92oh3_jKdNxTMP', 'type': 'IfcSpace'}`
    - **Space.-2.12 : Treppenhaus Ost - Ug[0-11]**: Space Validation
- Components Slab.-2.2.1 are inside the space.
- Space intersects with Slab.-1.5. The intersection area is 8.98 m2.
      - `{'guid': '1aFRCtje92oh3_jKdNxTMR', 'type': 'IfcSpace'}`
    - **Space.0.26 : Treppenhaus Ost - Og[2-26]**: Space Validation
- Components Slab.0.1 are inside the space.
      - `{'guid': '3DbdJyICv8GP1HEYzu7Wjo', 'type': 'IfcSpace'}`
    - **Space.0.7 : Treppenhaus West - Og[2-25]**: Space Validation
- Components Slab.0.2 are inside the space.
      - `{'guid': '3DbdJyICv8GP1HEYzu7WjO', 'type': 'IfcSpace'}`
    - **Space.-1.25 : Wc Damen West - Eg[1-15]**: Space Validation
- Components Wall.-1.19 are inside the space.
- Space intersects with Wall.-1.53. The intersection area is 0.17 m2.
- Space perimeter is not totally aligned with bounding components. 
      - `{'guid': '3DCde23Rb8uBrhrJgjcLQV', 'type': 'IfcSpace'}`
    - **Space.-1.11 : Wc Damen Ost - Eg[13]**: Space Validation
- Components Wall.-1.51 and Wall.-1.65 are inside the space.
- Space perimeter is not totally aligned with bounding components. The total length of these segments is 1.41 m.
      - `{'guid': '3DCde23Rb8uBrhrJgjcLQQ', 'type': 'IfcSpace'}`

**samuel_macalister_sample_house**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=0 FN=1
  - **False Negatives** (expected but missed): 1 GUIDs
    - **Space.0.2 : Living[106]**: Space Validation
- Components Roof.1.1.1 and Slab.1.1.1 are inside the space.
- Space doesn't touch slab, roof, or space surface below itself at all.
      - `{'guid': '3ch3OBgkrCEw4mDhJ2eOZ3', 'type': 'IfcSpace'}`

**wbdg_office**: F1=0.50 | P=1.00 R=0.33 | TP=2 FP=0 FN=4
  - **False Negatives** (expected but missed): 4 GUIDs
    - **Space.0.47 : Mens Rr[135]**: Space Validation
- Components Wall.0.10, Wall.0.4, Wall.0.5, Wall.0.6, and Wall.0.7 are inside the space.
- Space doesn't touch slab, roof, or space surface below itself at all.
      - `{'guid': '04Sq57eS5FffNezn2ilgsV', 'type': 'IfcSpace'}`
    - **Space.0.33 : Womens Rr[136]**: Space Validation
- Components Wall.0.11, Wall.0.17, and Wall.0.18 are inside the space.
- Space doesn't touch slab, roof, or space surface below itself at all.
      - `{'guid': '04Sq57eS5FffNezn2ilgrW', 'type': 'IfcSpace'}`
    - **Space.1.9 : Mens Rr[209]**: Space Validation
- Components Wall.1.131, Wall.1.142, and Wall.1.143 are inside the space.
- Space doesn't touch slab, roof, or space surface below itself at all.
      - `{'guid': '06njXbG3HC4RydTXssDqYj', 'type': 'IfcSpace'}`
    - **Space.1.8 : Womens Rr[207]**: Space Validation
- Components Wall.1.148 and Wall.1.149 are inside the space.
- Space doesn't touch slab, roof, or space surface below itself at all.
      - `{'guid': '06njXbG3HC4RydTXssDqYd', 'type': 'IfcSpace'}`


### space_validation_intersect — F1=0.444

**4351**: F1=0.40 | P=0.50 R=0.33 | TP=1 FP=1 FN=2
  - **False Positives** (predicted but not expected): 1 GUIDs
    - `{'guid': '2tMe7qG7n4XhDG_TV6Qihh', 'type': 'IfcSpace'}`
  - **False Negatives** (expected but missed): 2 GUIDs
    - **Space.0.2 : 1st Floor[4]**: Space Validation
- Space intersects with Wall.0.1 and Wall.0.6. The intersection area is 8.56 m2.
- Space perimeter is not totally aligned with bounding components. The total length of these segments 
      - `{'guid': '2tMe7qG7n4XhDG_TV6Qihi', 'type': 'IfcSpace'}`
    - **Space.2.1 : 3rd Floor[8]**: Space Validation
- Space intersects with Wall.0.6. The intersection area is 1.48 m2.
- Space touches slab, roof, or space surface below itself, but the area of touching is only 173.49 m2, which is 96%
      - `{'guid': '2tMe7qG7n4XhDG_TV6Qihy', 'type': 'IfcSpace'}`

**digital_hub**: F1=0.21 | P=0.12 R=1.00 | TP=6 FP=44 FN=0
  - **False Positives** (predicted but not expected): 44 GUIDs
    - `{'guid': '1aFRCtje92oh3_jKdNxTM0', 'type': 'IfcSpace'}`
    - `{'guid': '1aFRCtje92oh3_jKdNxTM1', 'type': 'IfcSpace'}`
    - `{'guid': '1aFRCtje92oh3_jKdNxTM3', 'type': 'IfcSpace'}`
    - `{'guid': '1aFRCtje92oh3_jKdNxTMP', 'type': 'IfcSpace'}`
    - `{'guid': '1aFRCtje92oh3_jKdNxTMQ', 'type': 'IfcSpace'}`
    - `{'guid': '1aFRCtje92oh3_jKdNxTMR', 'type': 'IfcSpace'}`
    - `{'guid': '1aFRCtje92oh3_jKdNxTMS', 'type': 'IfcSpace'}`
    - `{'guid': '1aFRCtje92oh3_jKdNxTMT', 'type': 'IfcSpace'}`
    - `{'guid': '1aFRCtje92oh3_jKdNxTMU', 'type': 'IfcSpace'}`
    - `{'guid': '1aFRCtje92oh3_jKdNxTMV', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQ0', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQ2', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQ3', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQ4', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQ5', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQ6', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQ7', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQ8', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQ9', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQB', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQE', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQQ', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQU', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQV', 'type': 'IfcSpace'}`
    - `{'guid': '3DCde23Rb8uBrhrJgjcLQr', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7WjO', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7WjP', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7WjQ', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7WjR', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7WjT', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7WjU', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7WjV', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7WjX', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7WjY', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7WjZ', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7Wja', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7Wjb', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7Wjc', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7Wjd', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7Wje', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7Wjf', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7Wjg', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7Wjh', 'type': 'IfcSpace'}`
    - `{'guid': '3DbdJyICv8GP1HEYzu7Wjo', 'type': 'IfcSpace'}`

**samuel_macalister_sample_house**: F1=0.96 | P=0.93 R=1.00 | TP=13 FP=1 FN=0
  - **False Positives** (predicted but not expected): 1 GUIDs
    - `{'guid': '3ch3OBgkrCEw4mDhJ2eOZ3', 'type': 'IfcSpace'}`

**wbdg_office**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=2 FN=0
  - **False Positives** (predicted but not expected): 2 GUIDs
    - `{'guid': '04Sq57eS5FffNezn2ilgC_', 'type': 'IfcSpace'}`
    - `{'guid': '04Sq57eS5FffNezn2ilgt8', 'type': 'IfcSpace'}`


### spaces_same_storey_same_bottom_elevation — F1=1.000 (PERFECT)
No errors on test models.

### unallocated_areas — F1=0.000

**4351**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=5 FN=0
  - **False Positives** (predicted but not expected): 5 GUIDs
    - `{'guid': '1neW5R2EX8$hGUNVKNOajs', 'type': 'IfcWallStandardCase'}`
    - `{'guid': '1neW5R2EX8$hGUNVKNOakd', 'type': 'IfcWallStandardCase'}`
    - `{'guid': '1o6iSxmUv8P91r$iXVGWXs', 'type': 'IfcWallStandardCase'}`
    - `{'guid': '1o6iSxmUv8P91r$iXVGZJQ', 'type': 'IfcWall'}`
    - `{'guid': '2iLpbw1JTCxhSAA5dilMd9', 'type': 'IfcWallStandardCase'}`

**digital_hub**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=5 FN=8
  - **False Positives** (predicted but not expected): 5 GUIDs
    - `{'guid': '09DVD6VyjAQPA6lucynkDP', 'type': 'IfcWall'}`
    - `{'guid': '12bPoIwbv0tBGfPfnvCUAC', 'type': 'IfcWall'}`
    - `{'guid': '12bPoIwbv0tBGfPfnvCUYu', 'type': 'IfcWall'}`
    - `{'guid': '12bPoIwbv0tBGfPfnvCUc2', 'type': 'IfcWall'}`
    - `{'guid': '12bPoIwbv0tBGfPfnvCUq4', 'type': 'IfcWall'}`
  - **False Negatives** (expected but missed): 8 GUIDs
    - **Unallocated Area (4.97 M2)**: Unallocated Areas
The unallocated area is 4.97 m2.
      - `{'guid': '3LF03GdXv2GhSTK1xTZzX0', 'type': 'IfcWall'}`
      - `{'guid': '3LF03GdXv2GhSTK1xTZzX3', 'type': 'IfcWall'}`
      - `{'guid': '3LF03GdXv2GhSTK1xTZzXC', 'type': 'IfcWall'}`
      - `{'guid': '3LF03GdXv2GhSTK1xTZzXD', 'type': 'IfcWall'}`
    - **Unallocated Area (4.97 M2)**: Unallocated Areas
The unallocated area is 4.97 m2.
      - `{'guid': '0YVU7tDBX86u6UVVsSmdwG', 'type': 'IfcWall'}`
      - `{'guid': '0YVU7tDBX86u6UVVsSmdwH', 'type': 'IfcWall'}`
      - `{'guid': '0YVU7tDBX86u6UVVsSmdwJ', 'type': 'IfcWall'}`
      - `{'guid': '0YVU7tDBX86u6UVVsSmdwK', 'type': 'IfcWall'}`

**samuel_macalister_sample_house**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=0 FN=12
  - **False Negatives** (expected but missed): 12 GUIDs
    - **Unallocated Area (8.40 M2)**: Unallocated Areas
The unallocated area is 8.40 m2.
      - `{'guid': '0NWseyvsH7_gBW225aGtuD', 'type': 'IfcWall'}`
      - `{'guid': '0NWseyvsH7_gBW225aGtwW', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '2OulbipBrAkwQNv_KJRUYY', 'type': 'IfcCurtainWall'}`
      - `{'guid': '2OulbipBrAkwQNv_KJRUgr', 'type': 'IfcCurtainWall'}`
      - `{'guid': '2hD3j_DmLBXxhCCy1gOWVy', 'type': 'IfcCurtainWall'}`
      - `{'guid': '38NblWsDL1I8DljLvn67bV', 'type': 'IfcWall'}`
      - `{'guid': '38NblWsDL1I8DljLvn67cw', 'type': 'IfcWall'}`
      - `{'guid': '39NeMDaWPEh9g8$CxWwg0v', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '3lIj7B0LnBjf0mvxk2zuuc', 'type': 'IfcColumn'}`
    - **Unallocated Area (8.66 M2)**: Unallocated Areas
The unallocated area is 8.66 m2.
      - `{'guid': '0lntrd6l1AGwfcnKJK5qmF', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '1jq3WIaE92UPTHNxmrWm6f', 'type': 'IfcWallStandardCase'}`
      - `{'guid': '38NblWsDL1I8DljLvn67bV', 'type': 'IfcWall'}`
      - `{'guid': '38NblWsDL1I8DljLvn67cE', 'type': 'IfcCurtainWall'}`
      - `{'guid': '38NblWsDL1I8DljLvn67cw', 'type': 'IfcWall'}`
      - `{'guid': '39NeMDaWPEh9g8$CxWwg0v', 'type': 'IfcWallStandardCase'}`

**wbdg_office**: F1=0.00 | P=0.00 R=0.00 | TP=0 FP=3 FN=0
  - **False Positives** (predicted but not expected): 3 GUIDs
    - `{'guid': '1b0OOEH1P4cx$jYCmjq8Ya', 'type': 'IfcWallStandardCase'}`
    - `{'guid': '1b0OOEH1P4cx$jYCmjqBV2', 'type': 'IfcWallStandardCase'}`
    - `{'guid': '27dLDsxMX8Sv5rKurGZzmr', 'type': 'IfcWallStandardCase'}`

