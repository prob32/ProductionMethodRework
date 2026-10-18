"""Company Culture node pictures (company_culture.ROW_ICONS, LINE_ICONS): vanilla 1.14 icons picked by what each picture
shows, per name row and tier (Pat 2026-10-18 22:28Z: "we can't have a rifle barrel representing steam winding").
GOOD: the picture shows that thing; OK: close; POOR: no vanilla picture fits, the nearest one stands in."""

ENG_ICONS = [
    # steel
    ('gfx/interface/icons/production_method_icons/blister_steel_process.dds',      # Hot Blast Stoves - OK (tall brick furnace stack)
     'gfx/interface/icons/production_method_icons/steamworks.dds',                 # Steam Blowing Engines - OK (steam engine, flywheel, chimney)
     'gfx/interface/icons/production_method_icons/open_hearth_process.dds'),       # Regenerative Furnaces - GOOD (Siemens open hearth = regenerative)
    # iron
    ('gfx/interface/icons/production_method_icons/coal_fired_plant.dds',           # Ore Roasting - OK (lumps beside a fire)
     'gfx/interface/icons/invention_icons/steam_donkey.dds',              # Steam Hoists - GOOD (vertical boiler with winch drums)
     'gfx/interface/icons/invention_icons/pneumatic_tools.dds'),          # Rock Drills - GOOD (rock drill on tripod)
    # coal
    ('gfx/interface/icons/invention_icons/shaft_mining.dds',              # Steam Winding - GOOD (pit headframe with winding sheave)
     'gfx/interface/icons/production_method_icons/chainsaws.dds',                  # Mechanical Cutters - OK (chain cutter bar)
     'gfx/interface/icons/production_method_icons/trains_electric.dds'),           # Electric Haulage - GOOD (electric locomotive)
    # lead
    ('gfx/interface/icons/invention_icons/rollers.dds',                   # Ore Dressing - OK (crushing-roll machine)
     'gfx/interface/icons/invention_icons/steam_donkey.dds',              # Steam Hoists - GOOD (steam winch / hoist)
     'gfx/interface/icons/production_method_icons/vaccum_brine_electrolysis.dds'), # Flotation Cells - OK (tank cell with feed pipes)
    # gold
    ('gfx/interface/icons/invention_icons/mechanized_workshops.dds',      # Stamp Mills - OK (steam hammer: vertical pounding stamp)
     'gfx/interface/icons/production_method_icons/hydroelectric_plant.dds',        # Hydraulic Sluicing - OK (water jets gushing from a works)
     'gfx/interface/icons/production_method_icons/leblanc_process.dds'),           # Cyanide Process - OK (chemical leach: flask pouring)
    # sulfur
    ('gfx/interface/icons/production_method_icons/condensing_engine_pump.dds',     # Steam Pumps - GOOD (beam pumping engine)
     'gfx/interface/icons/production_method_icons/blister_steel_process.dds',      # Ore Furnaces - OK (kiln furnace)
     'gfx/interface/icons/production_method_icons/simple_oil_extraction.dds'),     # Frasch Wells - OK (well derrick with gusher)
    # oil
    ('gfx/interface/icons/production_method_icons/simple_oil_extraction.dds',      # Cable-Tool Rigs - GOOD (wooden derrick)
     'gfx/interface/icons/production_method_icons/diesel_pump.dds',                # Rotary Drilling - OK (rig tower with engine wheel)
     'gfx/interface/icons/production_method_icons/pumps.dds'),                     # Gas Lift - OK (compressor/pump housing)
    # wood, hardwood
    ('gfx/interface/icons/production_method_icons/electric_saw_mills.dds',         # Steam Sawmills - OK (circular saw blade)
     'gfx/interface/icons/production_method_icons/log_carts.dds',                  # Logging Railways - GOOD (log wagon on rail wheels)
     'gfx/interface/icons/production_method_icons/saw_mills.dds'),                 # Band Saws - OK (long straight saw blade)
    # rubber
    ('gfx/interface/icons/invention_icons/rubber.dds',                    # Tapping Panels - GOOD (tapping cut and latex cup on trunk)
     'gfx/interface/icons/production_method_icons/home_workshops.dds',             # Smoke Houses - OK (shed with smoking chimney)
     'gfx/interface/icons/production_method_icons/plantation_production.dds'),     # Budded Clones - OK (nursery rows of young plants)
    # engines
    ('gfx/interface/icons/production_method_icons/lathes.dds',                     # Precision Lathes - GOOD (lathe)
     'gfx/interface/icons/production_method_icons/mechanized_workshops.dds',       # Machine Shops - GOOD (gear with hammer and wrench)
     'gfx/interface/icons/production_method_icons/assembly_lines.dds'),            # Assembly Lines - GOOD (conveyor line)
    # tools
    ('gfx/interface/icons/production_method_icons/mechanized_workshops.dds',       # Machine Tools - OK (machine-shop gear, hammer, wrench)
     'gfx/interface/icons/production_method_icons/lathes.dds',                     # Milling Machines - OK (machine tool; no milling cutter shown)
     'gfx/interface/icons/production_method_icons/precision_tools.dds'),           # Interchangeable Parts - OK (dividers / gauging)
    # clippers, manowars
    ('gfx/interface/icons/production_method_icons/reinforced_wooden_ships.dds',    # Composite Hulls - OK (reinforced wooden hull)
     'gfx/interface/icons/production_method_icons/electric_saw_mills.dds',         # Steam Saws - OK (circular saw blade)
     'gfx/interface/icons/production_method_icons/commerce_raiders.dds'),          # Patent Rigging - OK (sail plan and rigging foremost)
    # steamers, ironclads
    ('gfx/interface/icons/invention_icons/ironclad_tech.dds',             # Iron Hulls - GOOD (iron-hulled steamer)
     'gfx/interface/icons/production_method_icons/steamworks.dds',                 # Compound Engines - OK (steam engine)
     'gfx/interface/icons/production_method_icons/rotary_valve_engine.dds'),       # Triple Expansion - OK (larger steam engine with governor)
    # clothes
    ('gfx/interface/icons/production_method_icons/sewing_machines.dds',            # Sewing Machines - GOOD
     'gfx/interface/icons/production_method_icons/craftsman_sewing.dds',           # Cutting Tables - POOR: make: cloth layers spread on a long table, shears or band knife cutting pattern pieces
     'gfx/interface/icons/production_method_icons/electric_sewing_machines.dds'),  # Electric Sewing - GOOD
    # luxury_clothes
    ('gfx/interface/icons/production_method_icons/craftsman_sewing.dds',           # Pattern Cutting - OK (tailor's form and measuring rule)
     'gfx/interface/icons/production_method_icons/mechanized_looms.dds',           # Jacquard Trims - OK (power loom; punched cards not shown)
     'gfx/interface/icons/production_method_icons/handsewn_clothes.dds'),          # Couture Ateliers - OK (hand needlework)
    # fabric
    ('gfx/interface/icons/production_method_icons/mechanized_looms.dds',           # Power Looms - GOOD
     'gfx/interface/icons/production_method_icons/handsewn_clothes.dds',           # Ring Spinning - POOR: make: ring-spinning frame, row of upright spindles with yarn bobbins
     'gfx/interface/icons/production_method_icons/automatic_power_looms.dds'),     # Automatic Looms - GOOD
    # silk
    ('gfx/interface/icons/invention_icons/sericulture.dds',               # Rearing Houses - GOOD (silkworm on mulberry leaf)
     'gfx/interface/icons/invention_icons/modern_financial_instruments.dds',  # Reeling Machines - OK (wound reel on a stand with crank)
     'gfx/interface/icons/production_method_icons/steam_powered_evaporation.dds'), # Steam Filatures - OK (steam-heated vessel and pipes)
    # liquor
    ('gfx/interface/icons/production_method_icons/patent_stills.dds',              # Column Stills - GOOD (Coffey column still)
     'gfx/interface/icons/invention_icons/fractional_distillation.dds',   # Steam Distilling - OK (still with boiler)
     'gfx/interface/icons/production_method_icons/automated_bottle_blowers.dds'),  # Bottling Lines - GOOD (bottles moving down a line)
    # wine
    ('gfx/interface/icons/production_method_icons/pulp_pressing.dds',              # Press Machines - OK (press bearing down)
     'gfx/interface/icons/production_method_icons/flash_refrigerated.dds',         # Cellar Cooling - OK (cold: snowflake)
     'gfx/interface/icons/production_method_icons/automated_bottle_blowers.dds'),  # Bottling Lines - GOOD
    # groceries
    ('gfx/interface/icons/production_method_icons/canneries.dds',                  # Canning - GOOD
     'gfx/interface/icons/production_method_icons/flash_refrigerated.dds',         # Refrigeration - GOOD
     'gfx/interface/icons/production_method_icons/automated_bakery.dds'),          # Mechanised Bakeries - GOOD
    # sugar
    ('gfx/interface/icons/production_method_icons/vacuum_pan.dds',                 # Vacuum Pans - GOOD
     'gfx/interface/icons/production_method_icons/centrifugal_machine.dds',        # Centrifuges - GOOD
     'gfx/interface/icons/invention_icons/vulcanization.dds'),            # Diffusion Batteries - OK (riveted closed process vessel)
    # grain
    ('gfx/interface/icons/production_method_icons/plantation_production.dds',      # Seed Drills - OK (seedlings in drilled rows)
     'gfx/interface/icons/production_method_icons/harvesting_tools.dds',           # Reapers - OK (scythe; hand reaping, not the machine)
     'gfx/interface/icons/production_method_icons/steam_powered_threshers.dds'),   # Steam Threshers - GOOD
    # fruit
    ('gfx/interface/icons/production_method_icons/orchards.dds',                   # Grafted Orchards - OK (orchard fruit; grafting not shown)
     'gfx/interface/icons/production_method_icons/automatic_irrigation.dds',       # Irrigation - GOOD
     'gfx/interface/icons/production_method_icons/flash_refrigerated.dds'),        # Cold Storage - OK (snowflake: cold)
    # meat
    ('gfx/interface/icons/production_method_icons/open_air_stockyards.dds',        # Feedlots - OK (cattle in an open yard)
     'gfx/interface/icons/production_method_icons/refrigerated_rail_cars.dds',     # Refrigerated Cars - GOOD
     'gfx/interface/icons/production_method_icons/slaughterhouses.dds'),           # Packing Lines - OK (meat hook of the packing line)
    # fish
    ('gfx/interface/icons/production_method_icons/steam_trawlers.dds',             # Steam Trawlers - GOOD
     'gfx/interface/icons/production_method_icons/refrigerated_storage.dds',       # Ice Holds - OK (chilled fish)
     'gfx/interface/icons/production_method_icons/flash_refrigerated.dds'),        # Cold Storage - OK (snowflake)
    # tobacco, tea, coffee, opium, dye
    ('gfx/interface/icons/production_method_icons/home_workshops.dds',             # Curing Barns - OK (barn with smoking flue)
     'gfx/interface/icons/production_method_icons/electric_rollers.dds',           # Rolling Machines - OK (powered rollers)
     'gfx/interface/icons/production_method_icons/fertilization.dds'),             # Fertilised Estates - GOOD (fertiliser sack with plant)
    # artillery
    ('gfx/interface/icons/invention_icons/rifling.dds',                   # Rifled Barrels - GOOD
     'gfx/interface/icons/production_method_icons/breech_loading_artillery_production.dds',  # Breech Blocks - GOOD
     'gfx/interface/icons/production_method_icons/recoil_mechanism_artillery_production.dds'),  # Recoil Mechanisms - GOOD
    # small_arms
    ('gfx/interface/icons/invention_icons/rifling.dds',                   # Machine Rifling - GOOD (rifled barrel)
     'gfx/interface/icons/production_method_icons/precision_tools.dds',            # Interchangeable Parts - OK (dividers / gauging)
     'gfx/interface/icons/production_method_icons/lathes.dds'),                    # Automatic Lathes - GOOD (lathe)
    # ammunition
    ('gfx/interface/icons/invention_icons/percussion_cap.dds',            # Brass Drawing - OK (drawn brass cups)
     'gfx/interface/icons/production_method_icons/nitroglycerin.dds',              # Smokeless Powder - OK (nitro compound: drop and blast)
     'gfx/interface/icons/production_method_icons/explosive_shells.dds'),          # Belt Loading - OK (rounds side by side)
    # explosives
    ('gfx/interface/icons/production_method_icons/nitroglycerin.dds',              # Nitration Sheds - OK (nitroglycerin)
     'gfx/interface/icons/production_method_icons/ammonia_soda_process.dds',       # Contact Process - OK (chemical process: test tubes)
     'gfx/interface/icons/production_method_icons/vaccum_brine_electrolysis.dds'), # Continuous Nitration - OK (vessel with inflow/outflow pipes)
    # fertilizer
    ('gfx/interface/icons/production_method_icons/chemical_fertilizers.dds',       # Superphosphate Works - GOOD (acid poured on to make fertiliser)
     'gfx/interface/icons/production_method_icons/leblanc_process.dds',            # Lead Chambers - OK (acid process: flask pouring)
     'gfx/interface/icons/production_method_icons/nitrogen_fixation.dds'),         # Nitrogen Fixation - GOOD
    # glass
    ('gfx/interface/icons/production_method_icons/coal_fired_plant.dds',           # Tank Furnaces - OK (fired furnace)
     'gfx/interface/icons/production_method_icons/pulp_pressing.dds',              # Pressing Machines - OK (press bearing down)
     'gfx/interface/icons/production_method_icons/automated_bottle_blowers.dds'),  # Bottle Machines - GOOD
    # porcelain
    ('gfx/interface/icons/production_method_icons/blister_steel_process.dds',      # Tunnel Kilns - OK (bottle-kiln silhouette)
     'gfx/interface/icons/production_method_icons/molds.dds',                      # Jiggering - OK (clay in moulds)
     'gfx/interface/icons/invention_icons/chemical_bleaching.dds'),       # Transfer Printing - OK (pattern-printed plates)
    # paper
    ('gfx/interface/icons/invention_icons/rollers.dds',                   # Fourdrinier Machines - OK (feed table and roller train)
     'gfx/interface/icons/production_method_icons/pulp_pressing.dds',              # Wood Pulping - OK (pulp press)
     'gfx/interface/icons/production_method_icons/sulfite_pulping.dds'),           # Sulphite Process - GOOD
    # furniture, luxury_furniture
    ('gfx/interface/icons/production_method_icons/electric_saw_mills.dds',         # Steam Saws - OK (circular saw blade)
     'gfx/interface/icons/production_method_icons/luxury_furniture.dds',           # Bentwood - POOR: make: Thonet-style chair with curved steam-bent frame
     'gfx/interface/icons/production_method_icons/hardwood_selection.dds'),        # Veneering - OK (thin sheets of fine wood)
    # transportation
    ('gfx/interface/icons/production_method_icons/rail_transport.dds',             # Steel Rails - GOOD
     'gfx/interface/icons/production_method_icons/trains_steam.dds',               # Air Brakes - POOR: make: railway wheel with brake shoe and air-hose coupling
     'gfx/interface/icons/invention_icons/electrical_telegraph.dds'),     # Block Signalling - OK (block instrument / telegraph key)
    # merchant_marine
    ('gfx/interface/icons/production_method_icons/modern_port.dds',                # Steam Cranes - GOOD (dockside crane)
     'gfx/interface/icons/invention_icons/drydock.dds',                   # Dry Docks - GOOD
     'gfx/interface/icons/production_method_icons/industrial_port.dds'),           # Coaling Stations - OK (steamer at a bunkering port)
    # electricity
    ('gfx/interface/icons/production_method_icons/electric_engines.dds',           # Compound Dynamos - GOOD (dynamo with field coils)
     'gfx/interface/icons/invention_icons/steam_turbines.dds',            # Steam Turbines - GOOD
     'gfx/interface/icons/production_method_icons/electric_fencing.dds'),          # AC Transmission - OK (wires between posts carrying current)
    # telephones, radios
    ('gfx/interface/icons/production_method_icons/telephone_switchboards.dds',     # Switchboards - GOOD
     'gfx/interface/icons/invention_icons/modern_financial_instruments.dds',  # Loading Coils - OK (wound coil on a stand)
     'gfx/interface/icons/invention_icons/electrical_capacitors.dds'),    # Vacuum Tubes - OK (glowing glass bulbs)
    # automobiles
    ('gfx/interface/icons/production_method_icons/standardized_automobiles.dds',   # Assembly Lines - GOOD (cars on a conveyor)
     'gfx/interface/icons/production_method_icons/pulp_pressing.dds',              # Pressed Steel Bodies - OK (press bearing down)
     'gfx/interface/icons/production_method_icons/electric_engines.dds'),          # Electric Starters - OK (electric motor)
    # aeroplanes
    ('gfx/interface/icons/production_method_icons/aeroplanes.dds',                 # Metal Airframes - OK (aircraft; metal not shown)
     'gfx/interface/icons/production_method_icons/pumps.dds',                      # Wind Tunnels - POOR: make: tunnel with a model wing and airflow lines before a large fan
     'gfx/interface/icons/invention_icons/combustion_engine.dds'),        # Radial Engines - OK (internal-combustion engine, not radial)
    # tanks
    ('gfx/interface/icons/production_method_icons/arc_welded_buildings.dds',       # Welded Hulls - OK (arc-welding torch and sparks on plate)
     'gfx/interface/icons/invention_icons/compression_ignition.dds',      # Diesel Engines - GOOD
     'gfx/interface/icons/production_method_icons/tanks.dds'),                     # Torsion Bars - POOR: make: tank road wheels on a twisted torsion-bar suspension
]

EXP_ICONS = [
    # coal
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Coal Contracts - OK (money for goods: purchase deal)
     'gfx/interface/icons/production_method_icons/watertube_boiler.dds',           # Fuel Economisers - OK (boiler firebox)
     'gfx/interface/icons/invention_icons/shaft_mining.dds'),             # Captive Collieries - GOOD (pit headframe)
    # tools
    ('gfx/interface/icons/production_method_icons/trade_quantity_2.dds',           # Bulk Tool Orders - OK (crates exchanged)
     'gfx/interface/icons/production_method_icons/mechanized_workshops.dds',       # Tool Rooms - OK (workshop gear, hammer, wrench)
     'gfx/interface/icons/production_method_icons/pig_iron_tools.dds'),            # In-House Smithies - GOOD (hammer on anvil)
    # engines
    ('gfx/interface/icons/production_method_icons/steel_tools.dds',                # Maintenance Shops - OK (wrench and screwdriver)
     'gfx/interface/icons/production_method_icons/precision_tools.dds',            # Standard Patterns - OK (dividers / drafting)
     'gfx/interface/icons/production_method_icons/steamworks.dds'),                # Engine Pools - OK (steam engine)
    # oil
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Lubricant Contracts - OK (purchase deal)
     'gfx/interface/icons/invention_icons/dialectics.dds',                # Oil Recovery - OK (closed loop of arrows = recycling)
     'gfx/interface/icons/invention_icons/modern_sewerage.dds'),          # Pipeline Supply - OK (pipe runs)
    # electricity
    ('gfx/interface/icons/invention_icons/shift_work.dds',                # Load Scheduling - OK (time clock: scheduling)
     'gfx/interface/icons/production_method_icons/electric_engines.dds',           # Own Dynamos - GOOD (dynamo)
     'gfx/interface/icons/production_method_icons/power_plant.dds'),               # Grid Contracts - OK (power station)
    # transportation
    ('gfx/interface/icons/production_method_icons/rail_transport.dds',             # Rail Sidings - OK (rail track)
     'gfx/interface/icons/production_method_icons/trade_quantity_4.dds',           # Freight Contracts - OK (shipped cargo)
     'gfx/interface/icons/production_method_icons/tanker_cars.dds'),               # Private Wagons - OK (owner's rail wagon)
    # iron
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Ore Contracts - OK (purchase deal)
     'gfx/interface/icons/invention_icons/dialectics.dds',                # Scrap Recycling - OK (recycling loop)
     'gfx/interface/icons/invention_icons/shaft_mining.dds'),             # Captive Mines - GOOD (mine headframe)
    # steel
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Steel Contracts - OK (purchase deal)
     'gfx/interface/icons/invention_icons/dialectics.dds',                # Scrap Reuse - OK (recycling loop)
     'gfx/interface/icons/building_icons/steel_mills.dds'),              # Captive Mills - GOOD (steel mill with I-beam)
    # wood, hardwood
    ('gfx/interface/icons/invention_icons/bureaucracy.dds',               # Timber Concessions - OK (stamped grant papers)
     'gfx/interface/icons/production_method_icons/blister_steel_process.dds',      # Kiln Drying - OK (kiln)
     'gfx/interface/icons/building_icons/logging_camp.dds'),             # Own Forests - OK (logging camp and logs)
    # fabric
    ('gfx/interface/icons/production_method_icons/rayon.dds',                      # Bolt Contracts - OK (bolt of cloth)
     'gfx/interface/icons/production_method_icons/craftsman_sewing.dds',           # Cutting Patterns - OK (tailor's form and measuring rule)
     'gfx/interface/icons/invention_icons/dialectics.dds'),               # Remnant Reuse - OK (recycling loop)
    # explosives
    ('gfx/interface/icons/production_method_icons/trade_quantity_3.dds',           # Bulk Powder - OK (kegs and crates in bulk)
     'gfx/interface/icons/invention_icons/philosophical_pragmatism.dds',  # Blasting Schedules - OK (checklist clipboard)
     'gfx/interface/icons/production_method_icons/dynamite.dds'),                  # Controlled Charges - GOOD (charge with fuse)
    # rubber
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Latex Contracts - OK (purchase deal)
     'gfx/interface/icons/invention_icons/dialectics.dds',                # Reclaimed Rubber - OK (recycling loop)
     'gfx/interface/icons/invention_icons/rubber.dds'),                   # Own Estates - GOOD (tapped rubber tree)
    # dye
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Dye Contracts - OK (purchase deal)
     'gfx/interface/icons/production_method_icons/synthetic_dyes.dds',             # Fast Mordants - OK (chemical bottle and powder)
     'gfx/interface/icons/production_method_icons/dye_workshops.dds'),             # Own Dyeworks - GOOD (cloth over dye vat)
    # lead
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Lead Contracts - OK (purchase deal)
     'gfx/interface/icons/invention_icons/dialectics.dds',                # Scrap Lead - OK (recycling loop)
     'gfx/interface/icons/invention_icons/shaft_mining.dds'),             # Captive Mines - GOOD (mine headframe)
    # fertilizer
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Guano Contracts - OK (purchase deal)
     'gfx/interface/icons/production_method_icons/soil_enriching_farming.dds',     # Manure Recycling - OK (enriched soil with sprout)
     'gfx/interface/icons/production_method_icons/chemical_fertilizers.dds'),      # Own Works - OK (fertiliser works: flask on sprout)
    # silk
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Bale Contracts - OK (purchase deal)
     'gfx/interface/icons/production_method_icons/handsewn_clothes.dds',           # Waste Silk Spinning - OK (spool of spun thread)
     'gfx/interface/icons/invention_icons/sericulture.dds'),              # Own Filatures - OK (silkworm; the reeling mill not shown)
    # grain, sugar, meat, fish, fruit, tobacco, tea, coffee, opium
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Harvest Contracts - OK (purchase deal)
     'gfx/interface/icons/invention_icons/dialectics.dds',                # Waste Reduction - OK (recycling loop)
     'gfx/interface/icons/production_method_icons/plantation_production.dds'),     # Own Estates - OK (planted estate rows)
    # glass
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Glass Contracts - OK (purchase deal)
     'gfx/interface/icons/invention_icons/dialectics.dds',                # Cullet Recycling - OK (recycling loop)
     'gfx/interface/icons/building_icons/glassworks.dds'),               # Own Glassworks - GOOD (glassworks with panes)
    # sulfur
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Sulfur Contracts - OK (purchase deal)
     'gfx/interface/icons/production_method_icons/leblanc_process.dds',            # Acid Recovery - OK (acid flask pouring)
     'gfx/interface/icons/invention_icons/shaft_mining.dds'),             # Captive Mines - GOOD (mine headframe)
    # clippers, steamers, manowars, ironclads
    ('gfx/interface/icons/production_method_icons/trade_quantity_4.dds',           # Charter Contracts - OK (ship with cargo)
     'gfx/interface/icons/production_method_icons/basic_port.dds',                 # Fleet Pooling - OK (ships together in port)
     'gfx/interface/icons/production_method_icons/military_shipbuilding_steam.dds'),  # Own Fleet - OK (company steamer)
    # every other good
    ('gfx/interface/icons/production_method_icons/trade_quantity_1.dds',           # Supply Contracts - OK (purchase deal)
     'gfx/interface/icons/invention_icons/dialectics.dds',                # Waste Reduction - OK (recycling loop)
     'gfx/interface/icons/production_method_icons/simple_organization.dds'),       # Vertical Integration - OK (hierarchy chart)
]

UPS_ICONS = [
    # mines
    ('gfx/interface/icons/production_method_icons/picks_and_shovels.dds',          # Mine Captains - OK (mining; the overseer not shown)
     'gfx/interface/icons/production_method_icons/scholastic_education.dds',       # Mining School - OK (school building)
     'gfx/interface/icons/production_method_icons/ownership_academics.dds'),       # School of Mines - OK (academy with mortarboard)
    # heavy
    ('gfx/interface/icons/production_method_icons/pig_iron_tools.dds',             # Apprenticeships - OK (learning the trade at the anvil)
     'gfx/interface/icons/production_method_icons/ownership_academics.dds',        # Technical Institute - OK (academy with mortarboard)
     'gfx/interface/icons/production_method_icons/ammonia_soda_process.dds'),      # Works Laboratory - GOOD (test tubes)
    # light
    ('gfx/interface/icons/production_method_icons/standard_labor.dds',             # Foremen Training - OK (foreman over workers)
     'gfx/interface/icons/production_method_icons/scholastic_education.dds',       # Trade School - OK (school building)
     'gfx/interface/icons/production_method_icons/precision_tools.dds'),           # Works Engineers - OK (drafting dividers)
    # farms
    ('gfx/interface/icons/production_method_icons/chemical_fertilizers.dds',       # Agronomists - OK (soil science: flask on sprout)
     'gfx/interface/icons/production_method_icons/scholastic_education.dds',       # Farm School - OK (school building)
     'gfx/interface/icons/production_method_icons/ownership_academics.dds'),       # Agricultural College - OK (academy with mortarboard)
    # logging
    ('gfx/interface/icons/production_method_icons/homesteading.dds',               # Forest Wardens - OK (forester's lodge with tree)
     'gfx/interface/icons/production_method_icons/scholastic_education.dds',       # Forestry School - OK (school building)
     'gfx/interface/icons/production_method_icons/subsistence_farming.dds'),       # Silviculture - OK (hand tending a sapling)
    # oil
    ('gfx/interface/icons/production_method_icons/simple_oil_extraction.dds',      # Drillers' Training - OK (drilling derrick)
     'gfx/interface/icons/invention_icons/prospecting_tech.dds',          # Petroleum Geologists - OK (prospector's pick and samples)
     'gfx/interface/icons/production_method_icons/ammonia_soda_process.dds'),      # Research Station - OK (test tubes)
    # shipyards
    ('gfx/interface/icons/production_method_icons/wooden_buildings.dds',           # Shipwrights' Guild - OK (hammer, saw and plank)
     'gfx/interface/icons/production_method_icons/precision_tools.dds',            # Naval Architects - OK (drafting dividers)
     'gfx/interface/icons/production_method_icons/canals.dds'),                    # Model Basin - OK (water-filled basin)
    # rail
    ('gfx/interface/icons/production_method_icons/trains_steam.dds',               # Railway Engineers - OK (locomotive)
     'gfx/interface/icons/invention_icons/electrical_telegraph.dds',      # Signal School - OK (block / telegraph instrument)
     'gfx/interface/icons/building_icons/building_university.dds'),      # Electrical Institute - GOOD (institute with light bulb)
]

# Fixed lines: only those to change; every tier of a changed line is listed, unchanged tiers keep today's path.
# KEEP (already fits): fe Engineering (mechanical_tools), fx Expansion (manufacturies), ft Providence
# (currency_standards), sc Expanded Works I/II/Mass Production (mechanized_workshops, gantry_crane, conveyers),
# cz Colonization Charter (colonization), ho Company Housing/Model Dwellings (urbanization, urban_planning),
# tr Trade Charter (international_trade), iv Investment Charter (investment_banks), ch Industry Charter
# (corporate_charters), mo Monopoly Charter (power_of_the_purse), yi Labour-Saving Machinery (steam_turbines),
# ym Vertical Trust (stock_exchanges). Skipped: pg Hallmark Goods; g1/g2/xs/au take ENG/EXP/UPS_ICONS above.
LINE_ICONS = {
    'fs': ('gfx/interface/icons/production_method_icons/worker_cooperative.dds',),   # Stewardship - OK (handshake: employer and worker accord; was a militant fist)
    'sf': ('gfx/interface/icons/invention_icons/philosophical_pragmatism.dds',),  # Safety Rules - OK (rules checklist; was bloodied bandages)
    'fw': ('gfx/interface/icons/production_method_icons/privately_owned.dds',        # Fair Wages - OK (hand receiving pay; was a post box)
           'gfx/interface/icons/production_method_icons/power_of_the_purse.dds',     # Living Wage - OK (hand holding a full purse; was crowd and chart)
           'gfx/interface/icons/invention_icons/joint_stock_companies.dds'),  # Profit Sharing - GOOD (KEEP: partners over a shared pie)
    'ct': ('gfx/interface/icons/building_icons/urban_center.dds',),        # Company Town - OK (town square; was sewer pipes)
    'cl': ('gfx/interface/icons/invention_icons/shift_work.dds',            # Casual Labour I - OK (KEEP: clocking in)
           'gfx/interface/icons/production_method_icons/exploitative_practices.dds',  # Casual Labour II - OK (hand picking men from a crowd; was grass)
           'gfx/interface/icons/invention_icons/identification_documents.dds'),  # Casual Labour III - OK (KEEP: worker's papers)
    'tp': ('gfx/interface/icons/invention_icons/bureaucracy.dds',           # Tight Payroll I - OK (KEEP: stamped payroll papers)
           'gfx/interface/icons/invention_icons/macroeconomics.dds'),       # Tight Payroll II - OK (abacus counting costs; was a police truncheon)
    'ys': ('gfx/interface/icons/production_method_icons/furniture_handicraft.dds',),  # Master Craftsmen - OK (mallet and chisel; was a rock drill)
    'yt': ('gfx/interface/icons/invention_icons/international_diplomacy.dds',),  # Fair Supply Contracts - OK (handshake on a deal; was money stacks)
}
