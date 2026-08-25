/*
  Rupees, written the way people in India actually read them.

  toLocaleString("en-IN") gives 2,50,000 and not 250,000, which is the
  grouping every income certificate uses. Getting this wrong makes a
  number look like a different number at a glance.
*/

function money(amount) {
  if (amount === null || amount === undefined || amount === "") {
    return "-";
  }

  return `₹${Number(amount).toLocaleString("en-IN")}`;
}

/*
  The same number said out loud. 250000 becomes "2.5 lakh", which is how
  a student would describe their family income to another person.
*/
export function inWords(amount) {
  if (amount === null || amount === undefined || amount === "") {
    return "";
  }

  const value = Number(amount);

  if (value >= 10000000) {
    return `${(value / 10000000).toFixed(2).replace(/\.00$/, "")} crore`;
  }
  if (value >= 100000) {
    return `${(value / 100000).toFixed(2).replace(/\.00$/, "")} lakh`;
  }
  return String(value);
}

export default money;
