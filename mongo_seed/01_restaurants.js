// Synthetic teaching data, not real restaurants or inspection records.
// Re-running restores these eight documents only. It does not drop a database.
const course = db.getSiblingDB("stat315_nosql");
const restaurants = [
  {_id:"R01", name:"Northgate Noodles", cuisine:"Chinese", address:{area:"Northgate", street:"12 College Ave"}, price_band:1, dietary_options:["vegetarian","vegan"], inspection:{score:96}, outdoor_seating:true},
  {_id:"R02", name:"Campus Curry", cuisine:"Indian", address:{area:"Northgate", street:"24 College Ave"}, price_band:1, dietary_options:["vegetarian","vegan"], inspection:{score:98}},
  {_id:"R03", name:"Garden Table", cuisine:"Mediterranean", address:{area:"Downtown", street:"8 Main St"}, price_band:2, dietary_options:["vegetarian","vegan"], inspection:{score:99}, outdoor_seating:true},
  {_id:"R04", name:"Oak Street Grill", cuisine:"American", address:{area:"Northgate", street:"3 Oak St"}, price_band:2, dietary_options:["vegetarian"], inspection:{score:94}, outdoor_seating:false},
  {_id:"R05", name:"Library Cafe", cuisine:"Cafe", address:{area:"Campus", street:"1 Library Walk"}, price_band:1, dietary_options:["vegetarian"], inspection:{score:97}},
  {_id:"R06", name:"Market Tacos", cuisine:"Mexican", address:{area:"Northgate", street:"18 Market St"}, price_band:1, dietary_options:["vegetarian","vegan"], inspection:{score:93}, outdoor_seating:true},
  {_id:"R07", name:"River Sushi", cuisine:"Japanese", address:{area:"Riverside", street:"42 River Rd"}, price_band:3, dietary_options:["vegetarian"], inspection:{score:95}, outdoor_seating:false},
  {_id:"R08", name:"Green Bowl", cuisine:"Salads", address:{area:"Northgate", street:"9 Oak St"}, price_band:1, dietary_options:["vegetarian","vegan"], inspection:{score:97}, outdoor_seating:null}
];
for (const restaurant of restaurants) {
  course.restaurants.replaceOne({_id:restaurant._id}, restaurant, {upsert:true});
}
print("Loaded 8 synthetic restaurant documents into stat315_nosql.restaurants.");
