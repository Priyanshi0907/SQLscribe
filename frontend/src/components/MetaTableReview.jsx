import DescribeModal from "./DescribeModal";

/**
 * Shown right after database preparation completes — renders DescribeModal as a popup modal dialog over the live dashboard.
 */
export default function MetaTableReview({ dbName, isOpen = true, onContinue }) {
  return (
    <DescribeModal
      dbName={dbName}
      isModal={true}
      isOpen={isOpen}
      onClose={onContinue}
    />
  );
}
