/*
  The fixed lists the profile form uses.

  These match the values the database stores exactly. The backend upper
  cases whatever it is sent before comparing, but sending the right
  thing in the first place means a typo can never quietly return zero
  matches and look like an honest "nothing fits you".
*/

export const CATEGORIES = [
  { value: "SC", label: "SC - Scheduled Caste" },
  { value: "ST", label: "ST - Scheduled Tribe" },
  { value: "OBC", label: "OBC - Other Backward Class" },
  { value: "EWS", label: "EWS - Economically Weaker Section" },
  { value: "GEN", label: "General" },
  { value: "MINORITY", label: "Minority community" },
];

export const GENDERS = [
  { value: "FEMALE", label: "Female" },
  { value: "MALE", label: "Male" },
  { value: "OTHER", label: "Other" },
];

export const COURSE_LEVELS = [
  { value: "SCHOOL", label: "School (Class 9 to 12)" },
  { value: "DIPLOMA", label: "Diploma, ITI or Polytechnic" },
  { value: "UG", label: "Undergraduate (degree)" },
  { value: "PG", label: "Postgraduate" },
  { value: "PHD", label: "PhD or research" },
];

export const STATES = [
  "Andhra Pradesh",
  "Arunachal Pradesh",
  "Assam",
  "Bihar",
  "Chhattisgarh",
  "Goa",
  "Gujarat",
  "Haryana",
  "Himachal Pradesh",
  "Jharkhand",
  "Karnataka",
  "Kerala",
  "Madhya Pradesh",
  "Maharashtra",
  "Manipur",
  "Meghalaya",
  "Mizoram",
  "Nagaland",
  "Odisha",
  "Punjab",
  "Rajasthan",
  "Sikkim",
  "Tamil Nadu",
  "Telangana",
  "Tripura",
  "Uttar Pradesh",
  "Uttarakhand",
  "West Bengal",
  "Andaman and Nicobar",
  "Chandigarh",
  "Delhi",
  "Jammu and Kashmir",
  "Ladakh",
  "Lakshadweep",
  "Puducherry",
];
